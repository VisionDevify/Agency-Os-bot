from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.bot.navigation import screen_for_page
from app.models.audit import AuditLog
from app.models.event_log import EventLog
from app.models.reporting import AccountabilitySnapshot, DailyBriefing, NotificationTarget
from app.services.accounts import create_account
from app.services.auth import USER_STATUS_ACTIVE, assign_role_to_user, get_or_create_telegram_user, setup_owner_if_needed
from app.services.incidents import create_incident, resolve_incident
from app.services.model_brands import create_model_brand
from app.services.notifications import create_placeholder_notification_target, disable_notification_target
from app.services.operations import (
    calculate_accountability_score,
    executive_dashboard,
    generate_accountability_report,
    generate_daily_briefing,
    operations_dashboard,
    view_latest_daily_briefing,
)
from app.services.permissions import PermissionPrincipal, RoleName
from app.services.proxies import create_proxy
from app.services.tasks import complete_task, create_task
from tests.utils import session_scope


def _active_user(session, telegram_id: int, display_name: str):
    user = get_or_create_telegram_user(session, telegram_user_id=telegram_id, display_name=display_name)
    user.status = USER_STATUS_ACTIVE
    user.is_active = True
    return user


def test_executive_dashboard_v2_uses_database_counts() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        model = create_model_brand(session, actor=owner, display_name="Exec Model")
        account = create_account(session, model_brand=model, platform="instagram", username="exec", actor=owner)
        account.auth_status = "needs_login"
        proxy = create_proxy(
            session,
            actor=owner,
            provider="provider",
            host="proxy.local",
            port=8011,
            base_username="base",
            password="secret",
        )
        proxy.status = "critical"
        create_task(session, actor=owner, title="Overdue", due_at=datetime.now(UTC) - timedelta(days=1))
        create_incident(session, actor=owner, title="Critical incident", severity="critical", source_type="system")

        stats = executive_dashboard(session)

        assert stats["agency_health_score"] < 100
        assert stats["total_models"] == 1
        assert stats["total_accounts"] == 1
        assert stats["accounts_needing_login"] == 1
        assert stats["total_proxies"] == 1
        assert stats["critical_proxies"] == 1
        assert stats["overdue_tasks"] == 1
        assert stats["critical_incidents"] == 1


def test_daily_briefing_generation_latest_view_audit_and_event_log() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        model = create_model_brand(session, actor=owner, display_name="Briefing Model")
        create_account(session, model_brand=model, platform="x", username="briefing_x", actor=owner)

        briefing = generate_daily_briefing(session, actor=owner)
        latest = view_latest_daily_briefing(session, actor=owner)

        assert briefing["briefing_id"] == latest["briefing_id"]
        assert session.query(DailyBriefing).count() == 1
        assert session.query(AuditLog).filter_by(action="briefing.generated").count() == 1
        assert session.query(AuditLog).filter_by(action="briefing.viewed").count() == 1
        event = session.query(EventLog).filter_by(event_type="briefing.generated").one()
        assert event.metadata_json["agency_health_score"] == briefing["agency_health_score"]


def test_accountability_snapshot_generation_and_score() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        assignee = _active_user(session, 31, "Accountable")
        assign_role_to_user(session, assignee, RoleName.MANAGER)
        task = create_task(session, actor=owner, title="Complete me", assigned_to=assignee)
        complete_task(session, task, actor=owner)
        create_task(
            session,
            actor=owner,
            title="Late task",
            assigned_to=assignee,
            due_at=datetime.now(UTC) - timedelta(days=1),
        )
        incident = create_incident(
            session,
            actor=owner,
            title="Assigned incident",
            severity="critical",
            source_type="manual",
            assigned_to=assignee,
        )
        resolve_incident(session, incident, actor=assignee)

        report = generate_accountability_report(session, actor=owner)
        row = next(row for row in report["users"] if row["user_id"] == assignee.id)

        assert row["completed_tasks_today"] == 1
        assert row["overdue_tasks"] == 1
        assert row["resolved_incidents_today"] == 1
        assert row["score"] == calculate_accountability_score(
            assigned_open_tasks=1,
            completed_tasks_today=1,
            overdue_tasks_count=1,
            assigned_open_incidents=0,
            resolved_incidents_today=1,
        )
        assert session.query(AccountabilitySnapshot).filter_by(user_id=assignee.id).count() == 1
        assert session.query(EventLog).filter_by(event_type="accountability.generated").count() == 1


def test_operations_dashboard_counts_attention_items() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        model = create_model_brand(session, actor=owner, display_name="Ops Attention")
        account = create_account(session, model_brand=model, platform="email", username="ops@example.com", actor=owner)
        account.status = "critical"
        proxy = create_proxy(
            session,
            actor=owner,
            provider="provider",
            host="proxy2.local",
            port=8012,
            base_username="base",
            password="secret",
        )
        proxy.status = "warning"
        create_task(session, actor=owner, title="Blocked soon")
        create_incident(session, actor=owner, title="Warning incident", severity="warning", source_type="system")

        stats = operations_dashboard(session)

        assert stats["tasks_by_status"]["open"] == 1
        assert stats["incidents_by_severity"]["warning"] == 1
        assert stats["accounts_needing_attention"] == 1
        assert stats["proxies_needing_attention"] == 1


def test_department_dashboard_access_controls() -> None:
    with session_scope() as session:
        setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        chatter = _active_user(session, 41, "Chatter")
        assign_role_to_user(session, chatter, RoleName.CHATTER)
        restricted = _active_user(session, 42, "No Role")
        principal = PermissionPrincipal(telegram_id=chatter.telegram_id, role=RoleName.CHATTER)
        restricted_principal = PermissionPrincipal(telegram_id=restricted.telegram_id, role=RoleName.VIEWER)

        screen = screen_for_page("reports:chatter", principal, session=session, user=chatter)
        assert "Chatter Dashboard" in screen.text

        with pytest.raises(PermissionError):
            screen_for_page("reports:chatter", restricted_principal, session=session, user=restricted)

        denied = session.query(AuditLog).filter_by(action="access.denied", resource_id="reports:chatter").one()
        assert "view_chatter_dashboard" in denied.details["permission"]


def test_notification_target_placeholder_disable_and_event_log() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)

        target = create_placeholder_notification_target(session, actor=owner)
        disable_notification_target(session, target, actor=owner)

        assert target.is_active is False
        assert session.query(NotificationTarget).count() == 1
        assert session.query(EventLog).filter_by(event_type="notification_target.created").count() == 1
        assert session.query(EventLog).filter_by(event_type="notification_target.disabled").count() == 1
        assert "telegram_chat_id" not in session.query(AuditLog).filter_by(action="notification_target.created").one().details


def test_railway_config_and_docs_present() -> None:
    root = Path(__file__).resolve().parents[1]

    assert (root / "railway.json").exists()
    assert (root / "docs" / "railway_deployment.md").exists()
