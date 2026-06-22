import asyncio
import time

from app import main


def test_health_returns_degraded_when_database_check_times_out(monkeypatch) -> None:
    def slow_database_check(storage):
        time.sleep(0.05)
        return True, "late"

    monkeypatch.setattr(main, "HEALTH_CHECK_TIMEOUT_SECONDS", 0.001)
    monkeypatch.setattr(main, "_health_check_database", slow_database_check)
    monkeypatch.setattr(main.settings, "redis_url", "")

    payload = asyncio.run(main.health())

    assert payload["status"] == "degraded"
    assert payload["db"] == "unhealthy"
    assert payload["warning"] == "database_unavailable"
    assert payload["alembic_revision"] == "timeout"
