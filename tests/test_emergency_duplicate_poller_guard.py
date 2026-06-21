import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import app.bot.runner as bot_runner
from app.bot.screens.settings import (
    render_botstatus_page,
    render_production_observability_page,
    render_ui_self_test_page,
)
from app.bot.runner import TELEGRAM_DELIVERY_MODE, _record_bot_heartbeat, _watch_telegram_pending_updates
from app.core.config import settings
from app.services.bot_instances import (
    bot_instance_diagnostics,
    record_bot_instance_heartbeat,
    record_polling_conflict,
    telegram_polling_lock_key,
)
from app.services.heartbeats import record_heartbeat
from app.services.observability import production_observability_summary
from app.services.recommendations import list_recommendations
from app.services.system_truth import system_truth
from app.services.team_operations import BotPollingGuard
from app.services.auth import setup_owner_if_needed
from tests.utils import session_scope


SECRET_MARKERS = (
    "123456:secret-token",
    "TELEGRAM_BOT_TOKEN",
    "postgresql://user:pass",
    "redis://:password",
)


class _FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def set(self, key: str, value: str, *, nx: bool, ex: int) -> bool:
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    def get(self, key: str):
        return self.values.get(key)

    def eval(self, script: str, key_count: int, key: str, token: str, ttl: int | None = None) -> int:
        if self.values.get(key) != token:
            return 0
        if "del" in script:
            self.values.pop(key, None)
        return 1


class _FakeTelegramBot:
    def __init__(self, pending_counts: list[int], *, bump_update_marker_on_call: int | None = None) -> None:
        self.pending_counts = list(pending_counts)
        self.calls = 0
        self.bump_update_marker_on_call = bump_update_marker_on_call

    async def get_webhook_info(self):
        self.calls += 1
        if self.bump_update_marker_on_call == self.calls:
            bot_runner.LAST_TELEGRAM_UPDATE_MONOTONIC = bot_runner.LAST_TELEGRAM_UPDATE_MONOTONIC + 1
        if self.pending_counts:
            pending = self.pending_counts.pop(0)
        else:
            pending = 0
        return SimpleNamespace(pending_update_count=pending)


def _owner(session):
    return setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1, display_name="Rex")


def _production_env(monkeypatch) -> None:
    monkeypatch.setattr(settings, "database_url", "postgresql+psycopg://user:pass@example.com/db")
    monkeypatch.setattr(settings, "redis_url", "redis://:password@example")
    monkeypatch.setattr(settings, "bot_primary_instance", True)
    monkeypatch.setattr(settings, "git_commit", "abc123")
    monkeypatch.setenv("RAILWAY_PROJECT_ID", "project-test")
    monkeypatch.setenv("RAILWAY_SERVICE_NAME", "Bot Worker")


def _healthy_core_heartbeats(session) -> None:
    record_heartbeat(session, service_name="api", status="healthy", metadata={"source": "test"})
    record_heartbeat(session, service_name="db", status="healthy", metadata={"source": "test", "backend": "postgresql"})
    record_heartbeat(session, service_name="redis", status="healthy", metadata={"source": "test"})
    record_heartbeat(session, service_name="railway_deployment", status="healthy", metadata={"source": "test"})


def test_telegram_polling_lock_is_token_scoped_and_blocks_second_owner() -> None:
    fake_redis = _FakeRedis()
    key = telegram_polling_lock_key("123456:secret-token")
    first = BotPollingGuard("redis://local", key=key, owner_id="owner-one", client=fake_redis)
    second = BotPollingGuard("redis://local", key=key, owner_id="owner-two", client=fake_redis)

    assert key.startswith("telegram_polling_owner:")
    assert "secret-token" not in key
    assert first.acquire() is True
    assert second.acquire() is False
    assert second.current_owner() == "owner-one"
    assert first.refresh() is True
    first.release()
    assert second.acquire() is True


def test_polling_conflict_creates_event_recommendation_and_botstatus_warning(monkeypatch) -> None:
    _production_env(monkeypatch)
    with session_scope() as session:
        owner = _owner(session)
        _healthy_core_heartbeats(session)

        record_polling_conflict(
            session,
            instance_id="worker-secret-instance",
            reason="Another process is using the same Telegram bot token.",
            source="test",
            conflict_source="railway",
            polling_lock_owner="old-worker",
        )

        diagnostics = bot_instance_diagnostics(session, current_instance_id="worker-secret-instance")
        truth = system_truth(session)
        screen = render_botstatus_page(session, owner, current_instance_id="worker-secret-instance")
        details = render_botstatus_page(session, owner, current_instance_id="worker-secret-instance", details=True)
        recommendations = list_recommendations(session, status="open", limit=10)

        assert diagnostics["polling_conflict_active"] is True
        assert diagnostics["risk"] == "critical"
        assert truth.bot_polling_safe is False
        assert "Polling conflict detected" in screen.text
        assert "Critical" in screen.text
        assert "Another process is using the same Telegram bot token" in screen.text
        assert "Conflict Source: railway" in details.text
        assert any(item.recommendation_type == "bot_polling_conflict" for item in recommendations)
        for marker in SECRET_MARKERS:
            assert marker not in screen.text
            assert marker not in details.text


def test_polling_conflict_appears_in_observability_and_selftest(monkeypatch) -> None:
    _production_env(monkeypatch)
    with session_scope() as session:
        owner = _owner(session)
        _healthy_core_heartbeats(session)
        record_polling_conflict(
            session,
            instance_id="worker-secret-instance",
            reason="Another process is using the same Telegram bot token.",
            source="test",
            conflict_source="telegram_getupdates",
            polling_lock_owner="old-worker",
        )

        summary = production_observability_summary(session)
        observability = render_production_observability_page(session, owner)
        selftest = render_ui_self_test_page(session, owner, run_now=True)

        assert "bot_polling" in summary["system_truth_current_issue_codes"]
        assert summary["active_issue_count"] > 0
        assert "Another process is using the same Telegram bot token" in observability.text
        assert "Critical" in selftest.text
        assert "Telegram polling needs attention" in selftest.text
        for marker in SECRET_MARKERS:
            assert marker not in observability.text
            assert marker not in selftest.text


def test_polling_loop_does_not_clear_conflict_but_real_update_does(monkeypatch) -> None:
    _production_env(monkeypatch)
    with session_scope() as session:
        _healthy_core_heartbeats(session)
        record_polling_conflict(
            session,
            instance_id="worker-secret-instance",
            reason="Another process is using the same Telegram bot token.",
            source="test",
            conflict_source="telegram_getupdates",
            polling_lock_owner="old-worker",
        )

        _record_bot_heartbeat(session, status="healthy", source="polling_loop")
        assert bot_instance_diagnostics(session, current_instance_id="worker-secret-instance")["polling_conflict_active"] is True

        _record_bot_heartbeat(session, status="healthy", source="telegram_start")
        assert bot_instance_diagnostics(session, current_instance_id="worker-secret-instance")["polling_conflict_active"] is False


def test_webhook_delivery_does_not_count_as_duplicate_poller(monkeypatch) -> None:
    _production_env(monkeypatch)
    with session_scope() as session:
        _healthy_core_heartbeats(session)
        delivery_token = TELEGRAM_DELIVERY_MODE.set("webhook")
        try:
            _record_bot_heartbeat(session, status="healthy", source="telegram_start")
        finally:
            TELEGRAM_DELIVERY_MODE.reset(delivery_token)
        record_bot_instance_heartbeat(
            session,
            instance_id="old-polling-worker",
            status="healthy",
            metadata={
                "service_role": "worker",
                "primary": "True",
                "polling_allowed": "True",
                "polling_active": "True",
            },
        )

        diagnostics = bot_instance_diagnostics(session)

        assert diagnostics["webhook_delivery_active"] is True
        assert diagnostics["telegram_delivery_mode"] == "webhook"
        assert diagnostics["active_instance_count"] == 0
        assert diagnostics["duplicate_instance_count"] == 0
        assert diagnostics["risk"] != "no_active_polling_owner"


def test_pending_update_watchdog_exits_when_polling_is_wedged() -> None:
    bot = _FakeTelegramBot([2, 2])

    asyncio.run(
        _watch_telegram_pending_updates(
            bot,  # type: ignore[arg-type]
            interval_seconds=0,
            consecutive_limit=2,
            api_timeout_seconds=1,
            exit_process=False,
            max_checks=3,
        )
    )

    assert bot.calls == 2


def test_pending_update_watchdog_resets_after_real_update() -> None:
    bot = _FakeTelegramBot([2, 2, 0], bump_update_marker_on_call=2)

    async def run_watchdog() -> None:
        await _watch_telegram_pending_updates(
            bot,  # type: ignore[arg-type]
            interval_seconds=0,
            consecutive_limit=2,
            api_timeout_seconds=1,
            exit_process=False,
            max_checks=3,
        )

    asyncio.run(run_watchdog())

    assert bot.calls == 3
