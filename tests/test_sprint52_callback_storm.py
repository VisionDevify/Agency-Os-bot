import asyncio
import inspect

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


def test_callback_fingerprint_includes_navigation_version_and_optional_query_id() -> None:
    callback = FakeCallback(FakeMessage(10, message_id=123))
    callback.from_user = type("User", (), {"id": 1})()
    callback.data = "nav:proxies"
    callback.id = "callback-a"

    version_one = callback_fingerprint(callback, active_navigation_version="1")
    version_two = callback_fingerprint(callback, active_navigation_version="2")
    with_query_id = callback_fingerprint(
        callback,
        active_navigation_version="1",
        include_callback_query_id=True,
    )

    assert version_one != version_two
    assert with_query_id != version_one


def test_back_home_help_and_refresh_bypass_navigation_duplicate_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run() -> None:
        store = RedisIdempotencyStore()
        monkeypatch.setattr(runner, "CALLBACK_IDEMPOTENCY", store)
        with session_scope() as session:
            owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
            track_bot_message(session, chat_id=10, user=owner, message_id=123, screen="proxies")
            callback = FakeCallback(FakeMessage(10, message_id=123))
            callback.from_user = type("User", (), {"id": 1})()

            for page in ("menu", "help", "help:proxy_setup", "dashboard:refresh"):
                callback.data = f"nav:{page}"
                assert await runner._mark_navigation_callback_if_new(
                    callback,
                    session=session,
                    user=owner,
                    chat_id=10,
                    page=page,
                ) is True
                assert await runner._mark_navigation_callback_if_new(
                    callback,
                    session=session,
                    user=owner,
                    chat_id=10,
                    page=page,
                ) is True

    asyncio.run(run())


def test_rapid_duplicate_navigation_tap_is_short_debounced(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run() -> None:
        store = RedisIdempotencyStore()
        monkeypatch.setattr(runner, "CALLBACK_IDEMPOTENCY", store)
        with session_scope() as session:
            owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
            track_bot_message(session, chat_id=10, user=owner, message_id=123, screen="menu")
            callback = FakeCallback(FakeMessage(10, message_id=123))
            callback.from_user = type("User", (), {"id": 1})()
            callback.data = "nav:proxies"

            assert await runner._mark_navigation_callback_if_new(
                callback,
                session=session,
                user=owner,
                chat_id=10,
                page="proxies",
            ) is True
            assert await runner._mark_navigation_callback_if_new(
                callback,
                session=session,
                user=owner,
                chat_id=10,
                page="proxies",
            ) is False

            callback.data = "nav:opportunities"
            assert await runner._mark_navigation_callback_if_new(
                callback,
                session=session,
                user=owner,
                chat_id=10,
                page="opportunities",
            ) is True

    asyncio.run(run())


def test_navigation_idempotency_uses_current_session_after_start_cleanup(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run() -> None:
        store = RedisIdempotencyStore()
        monkeypatch.setattr(runner, "CALLBACK_IDEMPOTENCY", store)
        with session_scope() as session:
            owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
            track_bot_message(
                session,
                chat_id=10,
                user=owner,
                message_id=111,
                screen="menu",
                navigation_version=1,
            )
            new_version = await runner._cleanup_navigation_messages_on_start(
                type("Bot", (), {"delete_message": lambda self, chat_id, message_id: asyncio.sleep(0)})(),
                session,
                user=owner,
                chat_id=10,
            )
            track_bot_message(
                session,
                chat_id=10,
                user=owner,
                message_id=222,
                screen="menu",
                navigation_version=new_version,
            )
            callback = FakeCallback(FakeMessage(10, message_id=222))
            callback.from_user = type("User", (), {"id": 1})()
            callback.data = "nav:proxies"

            assert await runner._mark_navigation_callback_if_new(
                callback,
                session=session,
                user=owner,
                chat_id=10,
                page="proxies",
            ) is True

    asyncio.run(run())


def test_valid_navigation_duplicate_path_never_says_already_handled() -> None:
    source = inspect.getsource(runner.navigate) + inspect.getsource(runner._navigate_locked)
    assert "Already handled" not in source


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
