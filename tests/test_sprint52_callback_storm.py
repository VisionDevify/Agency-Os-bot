import asyncio

import pytest

import app.bot.runner as runner
from app.bot.screens.formatting import Screen
from app.services.auth import setup_owner_if_needed
from app.services.callback_protection import (
    CallbackLockManager,
    RedisIdempotencyStore,
    callback_fingerprint,
)
from app.services.chat_cleanup import is_stale_navigation_callback, track_bot_message
from tests.test_sprint45_chat_cleanup import FakeCallback, FakeMessage
from tests.utils import session_scope


def test_callback_lock_blocks_same_user_but_allows_three_users_same_chat() -> None:
    async def run() -> None:
        manager = CallbackLockManager()
        first = await manager.acquire_callback_lock(chat_id=10, user_id=1)
        assert first is not None
        assert await manager.acquire_callback_lock(chat_id=10, user_id=1) is None

        second = await manager.acquire_callback_lock(chat_id=10, user_id=2)
        third = await manager.acquire_callback_lock(chat_id=10, user_id=3)
        assert second is not None
        assert third is not None

        await manager.release(first)
        assert await manager.acquire_callback_lock(chat_id=10, user_id=1) is not None

    asyncio.run(run())


def test_message_edit_lock_blocks_same_message_edits() -> None:
    async def run() -> None:
        manager = CallbackLockManager()
        first = await manager.acquire_message_edit_lock(chat_id=10, message_id=99)
        assert first is not None
        assert await manager.acquire_message_edit_lock(chat_id=10, message_id=99) is None

        other_message = await manager.acquire_message_edit_lock(chat_id=10, message_id=100)
        assert other_message is not None

    asyncio.run(run())


def test_callback_fingerprint_idempotency_ignores_duplicate_taps() -> None:
    async def run() -> None:
        store = RedisIdempotencyStore()
        callback = FakeCallback(FakeMessage(10, message_id=123))
        callback.from_user = type("User", (), {"id": 1})()
        callback.data = "nav:proxies"
        fingerprint = callback_fingerprint(callback)

        assert await store.mark_callback_seen(fingerprint=fingerprint, ttl_seconds=90) is True
        assert await store.mark_callback_seen(fingerprint=fingerprint, ttl_seconds=90) is False
        assert await store.callback_seen(fingerprint) is True

    asyncio.run(run())


def test_state_action_idempotency_returns_existing_result() -> None:
    async def run() -> None:
        store = RedisIdempotencyStore()
        assert await store.reserve_action(action_type="backup", action_id="run-1", ttl_seconds=600) is True
        await store.store_action_result(
            action_type="backup",
            action_id="run-1",
            result={"status": "manual_required"},
            ttl_seconds=600,
        )
        assert await store.reserve_action(action_type="backup", action_id="run-1", ttl_seconds=600) is False
        assert await store.get_action_result(action_type="backup", action_id="run-1") == {
            "status": "manual_required"
        }

    asyncio.run(run())


def test_redis_failure_degrades_to_memory_locks() -> None:
    class FailingRedis:
        def set(self, *args, **kwargs):
            raise RuntimeError("redis down")

        def ping(self):
            raise RuntimeError("redis down")

    async def run() -> None:
        manager = CallbackLockManager(client=FailingRedis())
        lock = await manager.acquire_callback_lock(chat_id=10, user_id=1)
        assert lock is not None
        assert lock.backend == "memory"
        assert (await manager.health_check())["backend"] == "memory"
        assert manager.redis_degraded is True

    asyncio.run(run())


def test_stale_navigation_callback_is_detected() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        track_bot_message(session, chat_id=10, user=owner, message_id=11, screen="menu")
        track_bot_message(session, chat_id=10, user=owner, message_id=12, screen="proxies")

        assert is_stale_navigation_callback(session, chat_id=10, user=owner, message_id=11) is True
        assert is_stale_navigation_callback(session, chat_id=10, user=owner, message_id=12) is False


def test_safe_edit_wrapper_soft_answers_when_message_edit_lock_is_busy(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run() -> None:
        manager = CallbackLockManager()
        monkeypatch.setattr(runner, "CALLBACK_LOCKS", manager)
        held = await manager.acquire_message_edit_lock(chat_id=10, message_id=42)
        assert held is not None

        callback = FakeCallback(FakeMessage(10, message_id=42))
        result = await runner._edit_or_send_callback_screen(
            callback,
            Screen(text="Proxy Vault", reply_markup=None),
            page="proxies",
        )

        assert result.success is False
        assert result.outcome == "message_edit_locked"
        assert callback.answered == [("One moment - Fortuna is already updating that.", False)]

    asyncio.run(run())


def test_ten_duplicate_callback_fingerprints_only_process_once() -> None:
    async def run() -> None:
        store = RedisIdempotencyStore()
        callback = FakeCallback(FakeMessage(10, message_id=123))
        callback.from_user = type("User", (), {"id": 1})()
        callback.data = "nav:recovery_center"
        fingerprint = callback_fingerprint(callback)

        results = await asyncio.gather(
            *[
                store.mark_callback_seen(fingerprint=fingerprint, ttl_seconds=90)
                for _ in range(10)
            ]
        )

        assert results.count(True) == 1
        assert results.count(False) == 9

    asyncio.run(run())
