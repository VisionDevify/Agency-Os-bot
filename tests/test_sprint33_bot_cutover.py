from datetime import UTC, datetime, timedelta

from app.bot.screens import render_botstatus_page, render_integrity_page, render_ui_self_test_page
from app.core.config import settings
from app.runtime.railway_start import should_start_bot
from app.services.auth import setup_owner_if_needed
from app.services.bot_instances import bot_instance_diagnostics, polling_preflight
from app.services.heartbeats import record_heartbeat
from app.services.persistence import health_payload, storage_status
from tests.utils import session_scope


SECRET_MARKERS = (
    "secret-token",
    "postgresql://user:pass",
    "redis://:password",
    "TELEGRAM_BOT_TOKEN",
)


def _owner(session):
    return setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1, display_name="Rex")


def _bot_instance_metadata(
    *,
    role: str = "worker",
    polling_active: bool = True,
    polling_allowed: bool = True,
    primary: bool = True,
) -> dict[str, str]:
    return {
        "instance_id_masked": "test••test",
        "service_role": role,
        "polling_active": str(polling_active),
        "polling_allowed": str(polling_allowed),
        "primary": str(primary),
    }


def test_production_redis_missing_blocks_polling_by_default(monkeypatch) -> None:
    monkeypatch.setattr(settings, "database_url", "postgresql+psycopg://user:pass@example.com/db")
    monkeypatch.setattr(settings, "redis_url", "")
    monkeypatch.setattr(settings, "bot_primary_instance", True)
    monkeypatch.setattr(settings, "allow_polling_without_redis", False)
    monkeypatch.setenv("RAILWAY_PROJECT_ID", "project-test")

    preflight = polling_preflight()

    assert preflight.allowed is False
    assert "Redis is required" in preflight.reason


def test_redis_present_allows_primary_polling(monkeypatch) -> None:
    monkeypatch.setattr(settings, "database_url", "postgresql+psycopg://user:pass@example.com/db")
    monkeypatch.setattr(settings, "redis_url", "redis://example")
    monkeypatch.setattr(settings, "bot_primary_instance", True)
    monkeypatch.setattr(settings, "allow_polling_without_redis", False)
    monkeypatch.setenv("RAILWAY_PROJECT_ID", "project-test")

    assert polling_preflight().allowed is True


def test_bot_primary_instance_false_prevents_polling(monkeypatch) -> None:
    monkeypatch.setattr(settings, "database_url", "postgresql+psycopg://user:pass@example.com/db")
    monkeypatch.setattr(settings, "redis_url", "redis://example")
    monkeypatch.setattr(settings, "bot_primary_instance", False)
    monkeypatch.setenv("RAILWAY_PROJECT_ID", "project-test")

    preflight = polling_preflight()

    assert preflight.allowed is False
    assert "BOT_PRIMARY_INSTANCE is false" in preflight.reason


def test_runtime_launcher_blocks_railway_bot_without_redis() -> None:
    env = {
        "RAILWAY_ENVIRONMENT_ID": "prod",
        "TELEGRAM_BOT_TOKEN": "masked",
        "REDIS_URL": "",
    }

    assert should_start_bot(env) is False


def test_runtime_launcher_respects_non_primary_instance() -> None:
    env = {
        "RAILWAY_ENVIRONMENT_ID": "prod",
        "TELEGRAM_BOT_TOKEN": "masked",
        "REDIS_URL": "redis://example",
        "BOT_PRIMARY_INSTANCE": "false",
    }

    assert should_start_bot(env) is False


def test_health_ok_only_with_durable_db_and_healthy_redis() -> None:
    storage = storage_status(
        database_url="postgresql+psycopg://user:pass@example.com/db",
        allow_sqlite_fallback=False,
        environment="production",
    )

    healthy = health_payload(storage=storage, db_connected=True, redis_status="healthy")
    degraded = health_payload(storage=storage, db_connected=True, redis_status="unknown")

    assert healthy["status"] == "ok"
    assert healthy["db_backend"] == "postgresql"
    assert healthy["db_durable"] is True
    assert degraded["status"] == "degraded"
    assert "redis_unavailable" in degraded["warning"]


def test_duplicate_heartbeat_detection_warns(monkeypatch) -> None:
    monkeypatch.setattr(settings, "database_url", "postgresql+psycopg://user:pass@example.com/db")
    monkeypatch.setattr(settings, "redis_url", "redis://example")
    monkeypatch.setattr(settings, "bot_primary_instance", True)
    monkeypatch.setenv("RAILWAY_PROJECT_ID", "project-test")
    with session_scope() as session:
        record_heartbeat(
            session,
            service_name="bot_instance:first",
            status="healthy",
            metadata=_bot_instance_metadata(),
        )
        record_heartbeat(
            session,
            service_name="bot_instance:second",
            status="healthy",
            metadata=_bot_instance_metadata(),
        )

        diagnostics = bot_instance_diagnostics(session, current_instance_id="first")
        integrity = render_integrity_page(session, _owner(session))

        assert diagnostics["duplicate_instance_count"] == 1
        assert diagnostics["multiple_active_instances"] is True
        assert "Bot instances" in integrity.text
        assert "2 active bot instance heartbeat" in integrity.text


def test_one_active_worker_is_healthy(monkeypatch) -> None:
    monkeypatch.setattr(settings, "database_url", "postgresql+psycopg://user:pass@example.com/db")
    monkeypatch.setattr(settings, "redis_url", "redis://:password@example")
    monkeypatch.setattr(settings, "bot_primary_instance", True)
    monkeypatch.setenv("RAILWAY_PROJECT_ID", "project-test")
    with session_scope() as session:
        owner = _owner(session)
        record_heartbeat(
            session,
            service_name="bot",
            status="healthy",
            metadata={"redis_lock_status": "held", "polling_guard": "redis_lock"},
        )
        record_heartbeat(
            session,
            service_name="bot_instance:worker",
            status="healthy",
            metadata=_bot_instance_metadata(),
        )

        diagnostics = bot_instance_diagnostics(session, current_instance_id="worker")
        screen = render_botstatus_page(session, owner, current_instance_id="worker")

        assert diagnostics["active_instance_count"] == 1
        assert diagnostics["duplicate_instance_count"] == 0
        assert "Status:\nHealthy" in screen.text
        assert "Issues Found: 0" in screen.text


def test_worker_plus_api_heartbeat_is_healthy(monkeypatch) -> None:
    monkeypatch.setattr(settings, "database_url", "postgresql+psycopg://user:pass@example.com/db")
    monkeypatch.setattr(settings, "redis_url", "redis://:password@example")
    monkeypatch.setattr(settings, "bot_primary_instance", True)
    monkeypatch.setenv("RAILWAY_PROJECT_ID", "project-test")
    with session_scope() as session:
        owner = _owner(session)
        record_heartbeat(
            session,
            service_name="bot",
            status="healthy",
            metadata={"redis_lock_status": "held", "polling_guard": "redis_lock"},
        )
        record_heartbeat(
            session,
            service_name="bot_instance:worker",
            status="healthy",
            metadata=_bot_instance_metadata(),
        )
        record_heartbeat(
            session,
            service_name="bot_instance:api",
            status="healthy",
            metadata=_bot_instance_metadata(role="api", polling_active=False),
        )

        diagnostics = bot_instance_diagnostics(session, current_instance_id="worker")
        screen = render_botstatus_page(session, owner, current_instance_id="worker")
        details = render_botstatus_page(session, owner, current_instance_id="worker", details=True)

        assert diagnostics["active_instance_count"] == 1
        assert diagnostics["duplicate_instance_count"] == 0
        assert diagnostics["non_polling_instance_count"] == 1
        assert "Status:\nHealthy" in screen.text
        assert "Non-Polling Heartbeats: 1" in details.text


def test_stale_old_worker_heartbeat_is_healthy_with_details_only(monkeypatch) -> None:
    monkeypatch.setattr(settings, "database_url", "postgresql+psycopg://user:pass@example.com/db")
    monkeypatch.setattr(settings, "redis_url", "redis://:password@example")
    monkeypatch.setattr(settings, "bot_primary_instance", True)
    monkeypatch.setattr(settings, "bot_instance_active_seconds", 180)
    monkeypatch.setenv("RAILWAY_PROJECT_ID", "project-test")
    with session_scope() as session:
        owner = _owner(session)
        record_heartbeat(
            session,
            service_name="bot",
            status="healthy",
            metadata={"redis_lock_status": "held", "polling_guard": "redis_lock"},
        )
        record_heartbeat(
            session,
            service_name="bot_instance:worker",
            status="healthy",
            metadata=_bot_instance_metadata(),
        )
        stale = record_heartbeat(
            session,
            service_name="bot_instance:old-worker",
            status="healthy",
            metadata=_bot_instance_metadata(),
        )
        stale.last_seen_at = datetime.now(UTC) - timedelta(minutes=10)
        session.flush()

        diagnostics = bot_instance_diagnostics(session, current_instance_id="worker")
        screen = render_botstatus_page(session, owner, current_instance_id="worker")
        details = render_botstatus_page(session, owner, current_instance_id="worker", details=True)

        assert diagnostics["active_instance_count"] == 1
        assert diagnostics["duplicate_instance_count"] == 0
        assert diagnostics["stale_instance_count"] == 1
        assert stale.status == "stale"
        assert "Status:\nHealthy" in screen.text
        assert "Stale Bot Heartbeats: 1" in details.text

        selftest = render_ui_self_test_page(session, owner, run_now=True)
        assert "Telegram polling needs attention" not in selftest.text
        assert "duplicate poller" not in selftest.text.lower()


def test_bot_primary_false_heartbeat_does_not_count_as_active_poller(monkeypatch) -> None:
    monkeypatch.setattr(settings, "database_url", "postgresql+psycopg://user:pass@example.com/db")
    monkeypatch.setattr(settings, "redis_url", "redis://:password@example")
    monkeypatch.setattr(settings, "bot_primary_instance", True)
    monkeypatch.setenv("RAILWAY_PROJECT_ID", "project-test")
    with session_scope() as session:
        owner = _owner(session)
        record_heartbeat(
            session,
            service_name="bot",
            status="healthy",
            metadata={"redis_lock_status": "held", "polling_guard": "redis_lock"},
        )
        record_heartbeat(
            session,
            service_name="bot_instance:worker",
            status="healthy",
            metadata=_bot_instance_metadata(),
        )
        record_heartbeat(
            session,
            service_name="bot_instance:disabled-worker",
            status="healthy",
            metadata=_bot_instance_metadata(primary=False, polling_active=True, polling_allowed=False),
        )

        diagnostics = bot_instance_diagnostics(session, current_instance_id="worker")
        screen = render_botstatus_page(session, owner, current_instance_id="worker")

        assert diagnostics["active_instance_count"] == 1
        assert diagnostics["duplicate_instance_count"] == 0
        assert diagnostics["non_polling_instance_count"] == 1
        assert "Status:\nHealthy" in screen.text

        selftest = render_ui_self_test_page(session, owner, run_now=True)
        assert "Telegram polling needs attention" not in selftest.text
        assert "duplicate poller" not in selftest.text.lower()


def test_botstatus_renders_safe_instance_diagnostics(monkeypatch) -> None:
    monkeypatch.setattr(settings, "database_url", "postgresql+psycopg://user:pass@example.com/db")
    monkeypatch.setattr(settings, "redis_url", "redis://:password@example")
    monkeypatch.setattr(settings, "bot_primary_instance", True)
    monkeypatch.setenv("RAILWAY_PROJECT_ID", "project-test")
    with session_scope() as session:
        owner = _owner(session)
        record_heartbeat(
            session,
            service_name="bot",
            status="healthy",
            metadata={
                "redis_lock_status": "held",
                "polling_guard": "redis_lock",
                "last_telegram_update_at": datetime.now(UTC).isoformat(),
            },
        )

        screen = render_botstatus_page(session, owner, current_instance_id="bot-secret-instance")
        details = render_botstatus_page(session, owner, current_instance_id="bot-secret-instance", details=True)

        assert "Fortuna Bot Status" in screen.text
        assert "Status:" in screen.text
        assert "Recommended Action:" in screen.text
        assert "Fortuna Bot Status Technical Details" in details.text
        assert "Primary Polling: yes" in details.text
        assert "Redis Lock: held" in details.text
        assert "bot-secret-instance" not in screen.text
        assert "bot-secret-instance" not in details.text
        for marker in SECRET_MARKERS:
            assert marker not in screen.text
            assert marker not in details.text
