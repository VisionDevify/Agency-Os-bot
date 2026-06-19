import pytest
from sqlalchemy import func, select

from app.bot.navigation import screen_for_page
from app.bot.screens.errors import render_report_problem_page
from app.bot.screens.proxies import render_olympix_proxy_paste_page
from app.models.audit import AuditLog
from app.models.callback_error import CallbackErrorLog
from app.models.event_log import EventLog
from app.models.friction import FrictionItem
from app.models.recommendation import Recommendation
from app.models.task import Task
from app.models.team_rollout import AgencyActivationState
from app.services.agency_activation import run_activation_scan
from app.services.auth import setup_owner_if_needed
from app.services.friction import report_problem
from app.services.live_safety import LiveDataSafetyCheck, LiveDataSafetyStatus, live_data_safety_status
from app.services.permissions import PermissionPrincipal, RoleName
from app.services.persistence import storage_status
from app.services.setup_wizard import create_setup_model, update_setup_model_profile
from tests.utils import session_scope


def _owner(session):
    return setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1, display_name="Rex")


def _principal(owner):
    return PermissionPrincipal(telegram_id=owner.telegram_id, is_owner=True, role=RoleName.OWNER)


def _safe_status() -> LiveDataSafetyStatus:
    return LiveDataSafetyStatus(
        safe=True,
        checks=[
            LiveDataSafetyCheck("PostgreSQL durable", True, "ok"),
            LiveDataSafetyCheck("Redis healthy", True, "ok"),
            LiveDataSafetyCheck("Encryption enabled", True, "ok"),
            LiveDataSafetyCheck("Single bot instance", True, "ok"),
            LiveDataSafetyCheck("Polling safety", True, "ok"),
            LiveDataSafetyCheck("No SQLite fallback", True, "ok"),
        ],
    )


def _unsafe_status() -> LiveDataSafetyStatus:
    return LiveDataSafetyStatus(
        safe=False,
        checks=[
            LiveDataSafetyCheck("PostgreSQL durable", False, "Production storage must be durable PostgreSQL."),
            LiveDataSafetyCheck("Redis healthy", True, "ok"),
            LiveDataSafetyCheck("Encryption enabled", True, "ok"),
            LiveDataSafetyCheck("Single bot instance", True, "ok"),
            LiveDataSafetyCheck("Polling safety", True, "ok"),
            LiveDataSafetyCheck("No SQLite fallback", False, "SQLite emergency storage is not allowed for real credentials."),
        ],
    )


def test_live_data_safety_blocks_sqlite_fallback_before_real_secret_entry() -> None:
    storage = storage_status(
        database_url="sqlite+pysqlite:////tmp/fortuna_os.db",
        allow_sqlite_fallback=True,
        environment="railway",
    )
    with session_scope() as session:
        status = live_data_safety_status(
            session,
            storage=storage,
            redis_ping=lambda: True,
            encryption_ready=lambda: True,
        )

        assert status.safe is False
        assert "Production storage must be durable PostgreSQL." in status.blocking_reasons
        assert "SQLite emergency storage is not allowed for real credentials." in status.blocking_reasons


def test_live_data_safety_allows_real_secret_entry_only_when_storage_redis_encryption_and_polling_are_safe() -> None:
    storage = storage_status(
        database_url="postgresql+psycopg://user:pass@example.com/db",
        allow_sqlite_fallback=False,
        environment="production",
    )
    with session_scope() as session:
        status = live_data_safety_status(
            session,
            storage=storage,
            redis_ping=lambda: True,
            encryption_ready=lambda: True,
        )

        assert status.safe is True
        assert all(check.passed for check in status.checks)
        assert "user:pass" not in str(status)


def test_proxy_paste_screen_shows_guardrail_checklist_and_blocks_when_unsafe(monkeypatch) -> None:
    monkeypatch.setattr("app.bot.screens.proxies.live_data_safety_status", lambda session: _unsafe_status())
    with session_scope() as session:
        screen = render_olympix_proxy_paste_page(session)

        assert "Before you paste real proxy credentials" in screen.text
        assert "[fix] PostgreSQL durable" in screen.text
        assert "Real credential entry is blocked" in screen.text
        assert "host:port:username:password" not in screen.text
        assert "password" not in screen.text.lower() or "proxy credentials" in screen.text.lower()


def test_proxy_paste_screen_allows_input_when_safety_passes(monkeypatch) -> None:
    monkeypatch.setattr("app.bot.screens.proxies.live_data_safety_status", lambda session: _safe_status())
    with session_scope() as session:
        screen = render_olympix_proxy_paste_page(session)

        assert "[ok] PostgreSQL durable" in screen.text
        assert "Send one message in this format:" in screen.text
        assert "host:port:username:password" in screen.text
        assert "encrypted immediately" in screen.text


def test_manual_report_problem_creates_friction_audit_and_event_records() -> None:
    with session_scope() as session:
        owner = _owner(session)

        item = report_problem(
            session,
            actor=owner,
            screen="Proxy Vault",
            issue="Add Proxy button was confusing on mobile",
            severity="high",
            notes="Expected one paste import.",
            callback_error_log_id=123,
        )

        assert item.screen == "Proxy Vault"
        assert item.severity == "high"
        assert "CallbackErrorLog: 123" in item.issue
        assert session.scalar(select(AuditLog).where(AuditLog.action == "friction.reported")) is not None
        assert session.scalar(select(EventLog).where(EventLog.event_type == "friction.reported")) is not None


def test_callback_report_button_links_latest_failure_to_friction_item() -> None:
    with session_scope() as session:
        owner = _owner(session)
        principal = _principal(owner)
        error = CallbackErrorLog(
            telegram_user_id=owner.telegram_id,
            user_id=owner.id,
            callback_data="nav:proxy:broken",
            page="proxy:broken",
            affected_screen="Proxy Vault",
            exception_type="RuntimeError",
            error_message="safe renderer failure",
        )
        session.add(error)
        session.flush()

        screen = screen_for_page(f"callback_error:report:{error.id}", principal, session=session, user=owner)
        item = session.scalar(select(FrictionItem).where(FrictionItem.screen == "Proxy Vault"))

        assert "Problem Reported" in screen.text
        assert item is not None
        assert f"CallbackErrorLog: {error.id}" in item.issue
        assert "RuntimeError" in item.issue
        assert session.scalar(select(AuditLog).where(AuditLog.action == "callback.problem_reported")) is not None


def test_settings_report_problem_screen_guides_mobile_qa_input() -> None:
    intro = render_report_problem_page()
    started = render_report_problem_page(started=True)

    assert "Use this during mobile QA" in intro.text
    assert "Screen | what happened | severity | notes" in started.text
    assert "low, medium, high, or critical" in started.text


def test_model_live_data_validation_rejects_invalid_timezone_and_platform() -> None:
    with session_scope() as session:
        owner = _owner(session)

        with pytest.raises(ValueError, match="valid timezone"):
            create_setup_model(session, actor=owner, display_name="Invalid TZ", timezone="Mars/Olympus")

        with pytest.raises(ValueError, match="primary platform"):
            create_setup_model(session, actor=owner, display_name="Invalid Platform", primary_platform="threads")

        model = create_setup_model(
            session,
            actor=owner,
            display_name="Valid Model",
            timezone="America/New_York",
            primary_platform="Instagram",
        )
        assert model.primary_platform == "instagram"

        with pytest.raises(ValueError, match="display name"):
            update_setup_model_profile(session, model, actor=owner, display_name=" ")


def test_activation_scan_updates_readiness_without_duplicate_setup_tasks_or_recommendations() -> None:
    with session_scope() as session:
        owner = _owner(session)
        create_setup_model(session, actor=owner, display_name="Live QA Model")

        run_activation_scan(session, actor=owner)
        first_task_count = session.scalar(select(func.count()).select_from(Task).where(Task.title.like("Setup:%")))
        first_recommendation_count = session.scalar(
            select(func.count()).select_from(Recommendation).where(Recommendation.recommendation_type.like("activation_%"))
        )

        run_activation_scan(session, actor=owner)
        second_task_count = session.scalar(select(func.count()).select_from(Task).where(Task.title.like("Setup:%")))
        second_recommendation_count = session.scalar(
            select(func.count()).select_from(Recommendation).where(Recommendation.recommendation_type.like("activation_%"))
        )

        assert session.scalar(select(AgencyActivationState)) is not None
        assert first_task_count and first_task_count > 0
        assert first_recommendation_count and first_recommendation_count > 0
        assert first_task_count == second_task_count
        assert first_recommendation_count == second_recommendation_count
