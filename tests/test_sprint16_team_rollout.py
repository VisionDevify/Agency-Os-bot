from datetime import UTC, datetime, timedelta

from app.bot.navigation import screen_for_page
from app.bot.screens import (
    render_daily_experience_page,
    render_help_center_page,
    render_main_menu,
    render_notification_digest_mode_page,
    render_onboarding_page,
    render_performance_page,
    render_scheduled_automations_page,
    render_team_qa_page,
)
from app.models.automation import AutomationSchedule
from app.models.event_log import EventLog
from app.models.reporting import NotificationDeliveryAttempt
from app.models.team_rollout import NotificationDigest, TeamOnboardingChecklist
from app.services.auth import USER_STATUS_ACTIVE, assign_role_to_user, get_or_create_telegram_user, setup_owner_if_needed
from app.services.automations import (
    activate_automation_rule,
    approve_automation,
    create_automation_rule,
    request_automation_approval,
    simulate_automation_rule,
)
from app.services.notifications import create_delivery_attempt, create_notification_target
from app.services.permissions import PermissionPrincipal, RoleName
from app.services.tasks import create_task
from app.services.team_experience import (
    create_notification_digest,
    daily_experience,
    get_or_create_onboarding_checklist,
    list_onboarding_checklists,
    primary_role,
    role_home_items,
    run_due_scheduled_automations,
    update_onboarding_checklist,
)
from app.services.team_operations import set_availability, update_user_localization
from tests.utils import session_scope


def _owner(session):
    return setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1, display_name="Owner")


def _active_user(session, telegram_id: int, display_name: str):
    user = get_or_create_telegram_user(session, telegram_user_id=telegram_id, display_name=display_name)
    user.status = USER_STATUS_ACTIVE
    user.is_active = True
    return user


def test_role_specific_home_screens_hide_irrelevant_systems() -> None:
    with session_scope() as session:
        owner = _owner(session)
        manager = _active_user(session, 1601, "Manager")
        chatter = _active_user(session, 1602, "Chatter")
        va = _active_user(session, 1603, "VA")
        client = _active_user(session, 1604, "Client")
        assign_role_to_user(session, manager, RoleName.MANAGER, actor=owner)
        assign_role_to_user(session, chatter, RoleName.CHATTER, actor=owner)
        assign_role_to_user(session, va, RoleName.VA, actor=owner)
        assign_role_to_user(session, client, RoleName.MODEL_CLIENT, actor=owner)

        assert "Fortuna Automation" in {label for label, _ in role_home_items(owner)}
        manager_labels = {label for label, _ in role_home_items(manager)}
        assert {"Team", "Models", "Tasks", "Incidents", "Opportunities", "Reports"} <= manager_labels
        assert "Operations Dashboard" not in manager_labels
        chatter_labels = {label for label, _ in role_home_items(chatter)}
        va_labels = {label for label, _ in role_home_items(va)}
        client_labels = {label for label, _ in role_home_items(client)}

        assert primary_role(chatter) == "Chatter"
        assert {"My Models", "My Tasks", "My Opportunities", "Help"} <= chatter_labels
        assert "Proxies" not in chatter_labels
        assert "Automation" not in chatter_labels
        assert {"My Models", "My Accounts", "My Tasks", "Availability", "Help"} <= va_labels
        assert "Uploads" not in va_labels
        assert {"My Dashboard", "My Accounts", "My Reports", "My Team"} <= client_labels

        screen = render_main_menu(session, chatter)
        assert "Welcome back" in screen.text
        assert "Role: Chatter" in screen.text
        assert "Proxy" not in screen.text


def test_onboarding_flow_includes_role_intro_and_pending_access() -> None:
    with session_scope() as session:
        pending = get_or_create_telegram_user(session, telegram_user_id=1605, display_name="Pending User")

        update_user_localization(session, pending, actor=pending, language="Portuguese", require_admin=False)
        update_user_localization(session, pending, actor=pending, country="Brazil", require_admin=False)
        update_user_localization(session, pending, actor=pending, timezone="America/Sao_Paulo", require_admin=False)
        update_user_localization(session, pending, actor=pending, time_format="24h", require_admin=False)
        screen = render_onboarding_page(session, pending)

        assert "Access pending approval" in screen.text
        assert "Role Intro" in screen.text
        assert "America/Sao_Paulo" in screen.text


def test_daily_experience_and_performance_snapshot_use_real_tasks() -> None:
    with session_scope() as session:
        owner = _owner(session)
        chatter = _active_user(session, 1606, "Daily Chatter")
        assign_role_to_user(session, chatter, RoleName.CHATTER, actor=owner)
        set_availability(session, chatter, actor=chatter, status="on_shift")
        create_task(
            session,
            actor=owner,
            title="Due today",
            assigned_to=chatter,
            due_at=datetime.now(UTC) + timedelta(hours=2),
        )
        create_task(
            session,
            actor=owner,
            title="Overdue",
            assigned_to=chatter,
            due_at=datetime.now(UTC) - timedelta(hours=2),
        )

        data = daily_experience(session, chatter)
        today_screen = render_daily_experience_page(session, chatter)
        performance = render_performance_page(session, chatter)

        assert data["tasks_due_today"] >= 1
        assert data["overdue_items"] == 1
        assert "Good" in today_screen.text
        assert "Today's Priorities" in today_screen.text
        assert "Performance Snapshot" in performance.text
        assert "Accountability Score" in performance.text


def test_help_center_topics_render_for_staff_roles() -> None:
    with session_scope() as session:
        owner = _owner(session)
        va = _active_user(session, 1607, "Helpful VA")
        assign_role_to_user(session, va, RoleName.VA, actor=owner)

        screen = render_help_center_page(va)

        assert "Ask Fortuna" in screen.text
        labels = [button.text for row in screen.reply_markup.inline_keyboard for button in row]
        assert "What is a Task?" in labels
        assert "VA Help" in labels


def test_team_qa_checklist_updates_readiness_and_audits() -> None:
    with session_scope() as session:
        owner = _owner(session)
        user = _active_user(session, 1608, "Rollout User")

        checklist = get_or_create_onboarding_checklist(session, user)
        assert checklist.readiness_score < 100

        update_onboarding_checklist(session, user, actor=owner, field="role_assigned")
        update_onboarding_checklist(session, user, actor=owner, field="timezone_confirmed")
        update_onboarding_checklist(session, user, actor=owner, field="availability_configured")
        update_onboarding_checklist(session, user, actor=owner, field="help_center_viewed")
        update_onboarding_checklist(session, user, actor=owner, field="onboarded")

        refreshed = next(item for item in list_onboarding_checklists(session) if item.user_id == user.id)
        screen = render_team_qa_page(session)

        assert refreshed.readiness_score == 100
        assert session.query(TeamOnboardingChecklist).count() == 2
        assert "Rollout readiness" in screen.text


def test_notification_digest_mode_bundles_low_priority_updates() -> None:
    with session_scope() as session:
        owner = _owner(session)
        target = create_notification_target(
            session,
            actor=owner,
            name="Ops",
            target_type="telegram_group",
            purpose="operations",
            telegram_chat_id="12345",
        )
        create_delivery_attempt(session, target, event_type="task.assigned", actor=owner, status="pending")
        create_delivery_attempt(session, target, event_type="digest.sent", actor=owner, status="skipped")

        digest = create_notification_digest(session, actor=owner, user=owner)
        screen = render_notification_digest_mode_page(session, user=owner)

        assert digest.item_count == 2
        assert session.query(NotificationDigest).count() == 1
        assert session.query(NotificationDeliveryAttempt).count() == 2
        assert "Notification Digest Mode" in screen.text
        assert "2 update" in screen.text


def test_scheduled_low_risk_automation_runs_and_high_risk_skips() -> None:
    with session_scope() as session:
        owner = _owner(session)
        low_rule = create_automation_rule(
            session,
            actor=owner,
            name="Scheduled Low Risk",
            automation_type="scheduled_low_risk",
            trigger_type="scheduled",
            actions=[{"type": "write_event_log", "event_name": "scheduled.low_risk"}],
            risk_level="low",
        )
        simulate_automation_rule(session, low_rule, actor=owner)
        approval = request_automation_approval(session, low_rule, actor=owner)
        approve_automation(session, approval, actor=owner)
        activate_automation_rule(session, low_rule, actor=owner)
        high_rule = create_automation_rule(
            session,
            actor=owner,
            name="Scheduled High Risk",
            automation_type="scheduled_high_risk",
            trigger_type="scheduled",
            actions=[{"type": "rotate_proxy_session"}],
            risk_level="high",
            requires_owner_approval=True,
        )
        high_rule.status = "active"
        session.flush()
        now = datetime.now(UTC)
        session.add_all(
            [
                AutomationSchedule(
                    automation_rule_id=low_rule.id,
                    schedule_type="hourly",
                    is_active=True,
                    next_run_at=now - timedelta(minutes=1),
                ),
                AutomationSchedule(
                    automation_rule_id=high_rule.id,
                    schedule_type="hourly",
                    is_active=True,
                    next_run_at=now - timedelta(minutes=1),
                ),
            ]
        )
        session.flush()

        results = run_due_scheduled_automations(session, actor=owner, now=now)
        screen = render_scheduled_automations_page(session, user=owner)

        assert [result.status for result in results] == ["succeeded", "skipped"]
        assert session.query(EventLog).filter_by(event_type="scheduled.low_risk").count() == 1
        assert "Scheduled Automations" in screen.text
        assert "Skipped Runs: 1" in screen.text


def test_navigation_exposes_role_home_and_help_without_crashing() -> None:
    with session_scope() as session:
        owner = _owner(session)
        chatter = _active_user(session, 1609, "Nav Chatter")
        assign_role_to_user(session, chatter, RoleName.CHATTER, actor=owner)
        principal = PermissionPrincipal(telegram_id=chatter.telegram_id, role=RoleName.CHATTER)

        menu = screen_for_page("menu", principal, session=session, user=chatter)
        help_screen = screen_for_page("help", principal, session=session, user=chatter)

        assert "Role: Chatter" in menu.text
        assert "Ask Fortuna" in help_screen.text
