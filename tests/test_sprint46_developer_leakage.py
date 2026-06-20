from datetime import UTC, datetime

from sqlalchemy import text

from app.bot.screens.settings import render_audit_logs_page, render_production_observability_page
from app.core.config import settings
from app.models.audit import AuditLog
from app.services.auth import setup_owner_if_needed
from app.services.bot_instances import record_bot_instance_heartbeat
from app.services.heartbeats import record_heartbeat
from app.services.system_truth import expected_alembic_head, system_truth
from tests.utils import session_scope


def _owner(session):
    return setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1, display_name="Rex")


def _healthy_production_state(session, monkeypatch) -> None:
    monkeypatch.setattr(settings, "database_url", "postgresql+psycopg://user:pass@example.com/db")
    monkeypatch.setattr(settings, "redis_url", "redis://example")
    monkeypatch.setattr(settings, "bot_primary_instance", True)
    monkeypatch.setenv("RAILWAY_PROJECT_ID", "project-test")
    session.execute(text("create table alembic_version (version_num varchar(64) not null)"))
    session.execute(text("insert into alembic_version (version_num) values (:head)"), {"head": expected_alembic_head()})
    record_heartbeat(session, service_name="api", status="healthy", metadata={"source": "test"})
    record_heartbeat(session, service_name="db", status="healthy", metadata={"source": "test", "backend": "postgresql"})
    record_heartbeat(session, service_name="redis", status="healthy", metadata={"source": "test"})
    record_heartbeat(
        session,
        service_name="bot",
        status="healthy",
        metadata={
            "polling_guard": "redis_lock",
            "redis_lock_status": "held",
            "last_telegram_update_at": datetime.now(UTC).isoformat(),
        },
    )
    record_bot_instance_heartbeat(
        session,
        instance_id="primary-instance",
        metadata={"service_role": "worker", "polling_allowed": "True", "polling_active": "True"},
    )


def test_audit_logs_simple_screen_hides_raw_actions_and_targets() -> None:
    with session_scope() as session:
        owner = _owner(session)
        session.add(
            AuditLog(
                actor_user_id=owner.id,
                action="management_action.performed",
                resource_type="telegram_page",
                resource_id="settings",
                status="success",
                details={"telegram_id_masked": "12••34"},
            )
        )
        session.flush()

        screen = render_audit_logs_page(session, owner)

        assert "Recent Activity" in screen.text
        assert "Management area opened: Settings" in screen.text
        assert "management_action.performed" not in screen.text
        assert "telegram_page:settings" not in screen.text
        assert "Actor:" not in screen.text
        assert "Target:" not in screen.text


def test_audit_logs_technical_details_keep_raw_fields_without_secrets() -> None:
    with session_scope() as session:
        owner = _owner(session)
        session.add(
            AuditLog(
                actor_user_id=owner.id,
                action="management_action.performed",
                resource_type="telegram_page",
                resource_id="settings",
                status="success",
                details={"password": "hunter2", "safe": "value"},
            )
        )
        session.flush()

        details = render_audit_logs_page(session, owner, details=True)

        assert "Technical Logs" in details.text
        assert "Actor:" in details.text
        assert "Action: management_action.performed" in details.text
        assert "Target: telegram_page:settings" in details.text
        assert "hunter2" not in details.text
        assert "[redacted]" in details.text


def test_observability_hides_polling_warning_when_one_instance_and_redis_lock_are_healthy(monkeypatch) -> None:
    with session_scope() as session:
        owner = _owner(session)
        _healthy_production_state(session, monkeypatch)

        truth = system_truth(session)
        screen = render_production_observability_page(session, owner)

        assert truth.bot_polling_safe is True
        assert truth.production_ready is True
        assert "Bot polling safety needs attention" not in screen.text
        assert "Bot safety check needs review" not in screen.text
        assert "One bot instance is active" in screen.text


def test_observability_polling_warning_explains_duplicate_instance_cause(monkeypatch) -> None:
    with session_scope() as session:
        owner = _owner(session)
        _healthy_production_state(session, monkeypatch)
        record_bot_instance_heartbeat(
            session,
            instance_id="old-worker",
            metadata={"service_role": "worker", "polling_allowed": "True", "polling_active": "True"},
        )

        screen = render_production_observability_page(session, owner)

        assert "Bot safety check needs review" in screen.text
        assert "What Fortuna found:" in screen.text
        assert "More than one active bot instance was detected." in screen.text
        assert "Why it matters:" in screen.text
        assert "This prevents duplicate bot responses." in screen.text
        assert "What to do:" in screen.text
        assert "Bot polling safety needs attention" not in screen.text


def test_primary_health_screens_do_not_show_raw_telegram_page_targets(monkeypatch) -> None:
    with session_scope() as session:
        owner = _owner(session)
        _healthy_production_state(session, monkeypatch)
        session.add(
            AuditLog(
                actor_user_id=owner.id,
                action="admin_area.opened",
                resource_type="telegram_page",
                resource_id="intelligence",
                status="success",
                details={},
            )
        )
        session.flush()

        audit_screen = render_audit_logs_page(session, owner)
        observability = render_production_observability_page(session, owner)

        assert "telegram_page" not in audit_screen.text
        assert "admin_area.opened" not in audit_screen.text
        assert "telegram_page" not in observability.text
