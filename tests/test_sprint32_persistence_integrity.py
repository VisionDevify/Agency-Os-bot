import pytest

from app.bot.runner import _bot_heartbeat_metadata
from app.bot.screens import render_integrity_page, render_main_menu, render_production_observability_page
from app.core.config import settings
from app.services.auth import setup_owner_if_needed
from app.services.persistence import (
    enforce_sqlite_fallback_policy,
    health_payload,
    storage_status,
)
from tests.utils import session_scope


SECRET_MARKERS = ("secret-token", "proxy-password", "postgres://user:pass", "sqlite+pysqlite:////tmp/fortuna_os.db")


def _owner(session):
    return setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1, display_name="Rex")


def test_health_payload_shows_postgresql_backend() -> None:
    storage = storage_status(
        database_url="postgresql+psycopg://user:pass@example.com/db",
        allow_sqlite_fallback=False,
        environment="production",
    )

    payload = health_payload(storage=storage, db_connected=True, redis_status="healthy")

    assert payload["status"] == "ok"
    assert payload["app_name"] == "Fortuna OS"
    assert payload["environment"] == "production"
    assert payload["git_commit"] == "unknown"
    assert payload["build_version"] == "unknown"
    assert payload["deployed_at"] == "unknown"
    assert payload["alembic_revision"] == "unknown"
    assert payload["db"] == "healthy"
    assert payload["db_backend"] == "postgresql"
    assert payload["db_driver"] == "postgresql+psycopg"
    assert payload["db_durable"] is True
    assert "user:pass" not in str(payload)


def test_health_payload_includes_safe_build_metadata_without_secrets(monkeypatch) -> None:
    monkeypatch.setattr(settings, "git_commit", "198e746")
    monkeypatch.setattr(settings, "app_version", "v50.1")
    monkeypatch.setattr(settings, "deployed_at", "2026-06-19T12:00:00Z")
    storage = storage_status(
        database_url="postgresql+psycopg://user:pass@example.com/db",
        allow_sqlite_fallback=False,
        environment="production",
    )

    payload = health_payload(
        storage=storage,
        db_connected=True,
        redis_status="healthy",
        alembic_revision="0037_social_comment_profiles",
    )

    assert payload["git_commit"] == "198e746"
    assert payload["build_version"] == "v50.1"
    assert payload["deployed_at"] == "2026-06-19T12:00:00Z"
    assert payload["alembic_revision"] == "0037_social_comment_profiles"
    assert "user:pass" not in str(payload)
    assert "DATABASE_URL" not in str(payload)


def test_health_payload_uses_railway_commit_metadata_when_git_commit_missing(monkeypatch) -> None:
    monkeypatch.setattr(settings, "git_commit", None)
    monkeypatch.setattr(settings, "app_version", None)
    monkeypatch.setattr(settings, "deployed_at", None)
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "railway-safe-sha")
    storage = storage_status(
        database_url="postgresql+psycopg://user:pass@example.com/db",
        allow_sqlite_fallback=False,
        environment="production",
    )

    payload = health_payload(storage=storage, db_connected=True, redis_status="healthy")

    assert payload["git_commit"] == "railway-safe-sha"
    assert payload["build_version"] == "unknown"
    assert payload["deployed_at"] == "unknown"
    assert "RAILWAY_GIT_COMMIT_SHA" not in str(payload)
    assert "user:pass" not in str(payload)


def test_health_payload_redacts_suspicious_metadata(monkeypatch) -> None:
    monkeypatch.setattr(settings, "git_commit", "secret-token")
    monkeypatch.setattr(settings, "app_version", "DATABASE_URL=postgres://user:pass@example/db")
    monkeypatch.setattr(settings, "deployed_at", "redis://:password@example")
    storage = storage_status(
        database_url="postgresql+psycopg://user:pass@example.com/db",
        allow_sqlite_fallback=False,
        environment="production",
    )

    payload = health_payload(storage=storage, db_connected=True, redis_status="healthy")

    assert payload["git_commit"] == "unknown"
    assert payload["build_version"] == "unknown"
    assert payload["deployed_at"] == "unknown"
    for marker in SECRET_MARKERS:
        assert marker not in str(payload)


def test_health_payload_degrades_sqlite_fallback_in_production() -> None:
    storage = storage_status(
        database_url="sqlite+pysqlite:////tmp/fortuna_os.db",
        allow_sqlite_fallback=True,
        environment="railway",
    )

    payload = health_payload(storage=storage, db_connected=True, redis_status="unknown")

    assert payload["status"] == "degraded"
    assert payload["db"] == "degraded"
    assert payload["db_backend"] == "sqlite_fallback"
    assert payload["storage_warning"] == "production_persistence_degraded"
    assert "redis_unavailable" in payload["warning"]


def test_sqlite_fallback_blocked_by_default_in_production() -> None:
    storage = storage_status(
        database_url="sqlite+pysqlite:////tmp/fortuna_os.db",
        allow_sqlite_fallback=False,
        environment="railway",
    )

    with pytest.raises(RuntimeError):
        enforce_sqlite_fallback_policy(storage)


def test_sqlite_fallback_allowed_only_when_explicit() -> None:
    storage = storage_status(
        database_url="sqlite+pysqlite:////tmp/fortuna_os.db",
        allow_sqlite_fallback=True,
        environment="railway",
    )

    enforce_sqlite_fallback_policy(storage)
    assert storage.risk == "degraded"
    assert storage.sqlite_fallback_allowed is True


def test_observability_and_integrity_show_storage_without_secrets(monkeypatch) -> None:
    monkeypatch.setattr(settings, "database_url", "sqlite+pysqlite:////tmp/fortuna_os.db")
    monkeypatch.setattr(settings, "allow_sqlite_fallback", True)
    monkeypatch.setattr(settings, "redis_url", "")
    monkeypatch.setenv("RAILWAY_PROJECT_ID", "project-test")
    with session_scope() as session:
        owner = _owner(session)

        observability = render_production_observability_page(session, owner)
        integrity = render_integrity_page(session, owner)

        combined = observability.text + "\n" + integrity.text
        assert "SQLite Emergency" in combined
        assert "Production Integrity Check" in integrity.text
        assert "Redis URL is not configured" in integrity.text
        assert "No secrets" in integrity.text
        for marker in SECRET_MARKERS:
            assert marker not in combined


def test_owner_home_warns_when_production_uses_sqlite_fallback(monkeypatch) -> None:
    monkeypatch.setattr(settings, "database_url", "sqlite+pysqlite:////tmp/fortuna_os.db")
    monkeypatch.setattr(settings, "allow_sqlite_fallback", True)
    monkeypatch.setenv("RAILWAY_PROJECT_ID", "project-test")
    with session_scope() as session:
        owner = _owner(session)

        screen = render_main_menu(session, owner)

        assert "Production Degraded" in screen.text
        assert "emergency storage mode" in screen.text


def test_bot_heartbeat_metadata_does_not_pretend_redis_guard_without_redis(monkeypatch) -> None:
    monkeypatch.setattr(settings, "database_url", "sqlite+pysqlite:////tmp/fortuna_os.db")
    monkeypatch.setattr(settings, "allow_sqlite_fallback", True)
    monkeypatch.setattr(settings, "redis_url", "")
    monkeypatch.setenv("RAILWAY_PROJECT_ID", "project-test")

    metadata = _bot_heartbeat_metadata("startup")

    assert metadata["db_backend"] == "sqlite_fallback"
    assert metadata["polling_guard"] == "disabled_no_redis"
    assert metadata["redis_lock_status"] == "not_configured"
    assert "password" not in str(metadata).lower()
