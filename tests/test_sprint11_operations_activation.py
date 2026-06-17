from datetime import UTC, datetime, time, timedelta

from app.bot.navigation import screen_for_page
from app.bot.screens import render_manager_command_page, render_onboarding_page
from app.models.audit import AuditLog
from app.models.event_log import EventLog
from app.models.incident import IncidentTimeline
from app.models.reporting import NotificationDeliveryAttempt
from app.services.auth import (
    USER_STATUS_ACTIVE,
    get_or_create_telegram_user,
    setup_owner_if_needed,
)
from app.services.incidents import (
    create_incident,
    escalate_incident,
    incident_timeline,
    investigate_incident,
    resolve_incident,
)
from app.services.notifications import create_notification_target
from app.services.operations import generate_daily_digest, request_digest_send
from app.services.permissions import PermissionPrincipal, RoleName
from app.services.tasks import (
    assign_task,
    create_task,
    escalate_task,
    overdue_tasks,
    record_overdue_tasks,
)
from app.services.team_operations import (
    BotPollingGuard,
    format_user_datetime,
    get_or_create_availability,
    is_user_available,
    manager_command_metrics,
    onboarding_next_step,
    set_availability,
    smart_notification_decision,
    update_user_localization,
)
from tests.utils import session_scope


def _owner(session):
    return setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)


def _active_user(session, telegram_id: int, display_name: str):
    user = get_or_create_telegram_user(session, telegram_user_id=telegram_id, display_name=display_name)
    user.status = USER_STATUS_ACTIVE
    user.is_active = True
    return user


def test_pending_user_localization_onboarding_flow() -> None:
    with session_scope() as session:
        pending = get_or_create_telegram_user(session, telegram_user_id=501, display_name="Pending VA")

        assert pending.status == "pending"
        assert onboarding_next_step(pending) == "language"
        assert "Select your language" in render_onboarding_page(session, pending).text

        update_user_localization(session, pending, actor=pending, language="Spanish", require_admin=False)
        assert onboarding_next_step(pending) == "country"
        update_user_localization(session, pending, actor=pending, country="Colombia", require_admin=False)
        assert onboarding_next_step(pending) == "timezone"
        update_user_localization(session, pending, actor=pending, timezone="America/Bogota", require_admin=False)
        assert onboarding_next_step(pending) == "pending_approval"
        update_user_localization(session, pending, actor=pending, time_format="24h", require_admin=False)

        screen = render_onboarding_page(session, pending)

        assert "Access pending approval" in screen.text
        assert "Spanish" in screen.text
        assert "America/Bogota" in screen.text
        assert session.query(AuditLog).filter_by(action="user.language_updated").count() == 1
        assert session.query(AuditLog).filter_by(action="user.timezone_updated").count() == 1


def test_timezone_formatting_and_availability_quiet_hours() -> None:
    with session_scope() as session:
        owner = _owner(session)
        user = _active_user(session, 502, "Shift User")
        update_user_localization(
            session,
            user,
            actor=owner,
            timezone="Asia/Manila",
            time_format="24h",
        )
        set_availability(
            session,
            user,
            actor=user,
            status="on_shift",
            quiet_hours_start_local=time(22, 0),
            quiet_hours_end_local=time(7, 0),
        )

        assert "20:30" in format_user_datetime(user, datetime(2026, 6, 17, 12, 30, tzinfo=UTC))
        assert is_user_available(user, now=datetime(2026, 6, 17, 12, 30, tzinfo=UTC)) is True
        assert is_user_available(user, now=datetime(2026, 6, 17, 16, 0, tzinfo=UTC)) is False
        assert get_or_create_availability(session, user).status == "on_shift"
        assert session.query(AuditLog).filter_by(action="availability.updated").count() == 1


def test_task_assignment_escalation_and_overdue_detection() -> None:
    with session_scope() as session:
        owner = _owner(session)
        assignee = _active_user(session, 503, "Ops Assignee")
        task = create_task(
            session,
            actor=owner,
            title="Handle overdue ops item",
            assigned_to=assignee,
            due_at=datetime.now(UTC) - timedelta(hours=2),
        )

        assert task.owner_user_id == owner.id
        assert task in overdue_tasks(session)

        assign_task(session, task, assignee, actor=owner)
        escalate_task(session, task, actor=owner)
        detected = record_overdue_tasks(session, actor=owner)

        assert task.assigned_to_user_id == assignee.id
        assert task.escalation_level == 1
        assert task.last_escalated_at is not None
        assert detected == 1
        assert session.query(AuditLog).filter_by(action="task.escalated").count() == 1
        assert session.query(EventLog).filter_by(event_type="task.overdue_detected").count() == 1


def test_incident_timeline_status_changes_and_escalation() -> None:
    with session_scope() as session:
        owner = _owner(session)
        assignee = _active_user(session, 504, "Incident Lead")
        incident = create_incident(
            session,
            actor=owner,
            title="Critical operations issue",
            severity="critical",
            source_type="system",
            assigned_to=assignee,
        )

        investigate_incident(session, incident, actor=owner)
        escalate_incident(session, incident, actor=owner)
        resolve_incident(session, incident, actor=owner, resolution_notes="Resolved in test.")

        entries = incident_timeline(session, incident)
        event_types = {entry.event_type for entry in entries}

        assert incident.owner_user_id == owner.id
        assert incident.status == "resolved"
        assert incident.escalation_level == 1
        assert {"incident.created", "incident.investigating", "incident.escalated", "incident.resolved"} <= event_types
        assert session.query(IncidentTimeline).count() == 4


def test_smart_notification_routing_respects_unavailable_users() -> None:
    with session_scope() as session:
        owner = _owner(session)
        assignee = _active_user(session, 505, "Quiet User")
        create_notification_target(
            session,
            actor=owner,
            name="Operations",
            target_type="telegram_group",
            purpose="operations",
            telegram_chat_id="-100111222333",
        )
        set_availability(
            session,
            assignee,
            actor=assignee,
            status="on_shift",
            timezone="UTC",
            quiet_hours_start_local=time(0, 0),
            quiet_hours_end_local=time(23, 59),
        )

        decision = smart_notification_decision(
            session,
            event_type="task.assigned",
            assigned_user=assignee,
            now=datetime(2026, 6, 17, 12, 0, tzinfo=UTC),
        )

        assert decision.direct_user_allowed is False
        assert "operations" in decision.purposes
        assert decision.reason == "assigned_user_unavailable_routed_to_operations"


def test_daily_digest_delivery_attempt_and_manager_command_metrics() -> None:
    with session_scope() as session:
        owner = _owner(session)
        assignee = _active_user(session, 506, "Manager Report User")
        create_notification_target(
            session,
            actor=owner,
            name="HQ",
            target_type="telegram_group",
            purpose="owner",
            telegram_chat_id="-100444555666",
        )
        create_notification_target(
            session,
            actor=owner,
            name="Operations",
            target_type="telegram_group",
            purpose="operations",
            telegram_chat_id="-100777888999",
        )
        set_availability(session, assignee, actor=assignee, status="on_shift")
        create_task(session, actor=owner, title="Open team task", assigned_to=assignee)
        create_incident(session, actor=owner, title="Open team incident", assigned_to=assignee, severity="critical")

        digest = generate_daily_digest(session, actor=owner)
        attempts = request_digest_send(session, actor=owner, purpose="operations")
        metrics = manager_command_metrics(session)
        screen = render_manager_command_page(session, user=owner)

        assert digest["agency_health_score"] >= 0
        assert attempts == 1
        assert metrics["open_tasks"] == 1
        assert metrics["open_incidents"] == 1
        assert metrics["unresolved_critical_incidents"] == 1
        assert "Manager Command View" in screen.text
        assert session.query(NotificationDeliveryAttempt).count() == 1
        assert session.query(EventLog).filter_by(event_type="digest.sent").count() == 1


def test_navigation_availability_callback_and_production_status_screen() -> None:
    with session_scope() as session:
        owner = _owner(session)
        principal = PermissionPrincipal(telegram_id=owner.telegram_id, is_owner=True, role=RoleName.OWNER)

        availability = screen_for_page("availability:set:away", principal, session=session, user=owner)
        production = screen_for_page("production_status", principal, session=session, user=owner)

        assert "My Availability" in availability.text
        assert get_or_create_availability(session, owner).status == "away"
        assert "Bot Status" in production.text


class _FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def set(self, key: str, value: str, *, nx: bool, ex: int) -> bool:
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    def eval(self, script: str, key_count: int, key: str, token: str, ttl: int | None = None) -> int:
        if self.values.get(key) != token:
            return 0
        if "del" in script:
            self.values.pop(key, None)
        return 1


def test_bot_polling_guard_blocks_duplicate_and_releases() -> None:
    fake_redis = _FakeRedis()
    first = BotPollingGuard("redis://local", client=fake_redis)
    second = BotPollingGuard("redis://local", client=fake_redis)

    assert first.acquire() is True
    assert second.acquire() is False
    assert first.refresh() is True
    first.release()
    assert second.acquire() is True
