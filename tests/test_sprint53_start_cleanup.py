import asyncio

from app.bot.runner import (
    _cleanup_navigation_messages_on_start,
    _send_tracked_navigation_message,
    _send_tracked_temporary_message,
)
from app.bot.screens.formatting import Screen
from datetime import UTC, datetime

from app.models.chat import (
    MESSAGE_LABELS,
    PRESERVED_MESSAGE_LABELS,
    TEMPORARY_ERROR,
    TEMPORARY_HELP,
    TEMPORARY_MESSAGE_LABELS,
    TEMPORARY_NAVIGATION,
    TEMPORARY_STATUS,
    UNKNOWN_PRESERVE,
    BotChatMessage,
    ChatCleanupRun,
)
from app.services.observability import production_observability_summary
from app.services.auth import get_or_create_telegram_user, setup_owner_if_needed
from app.services.chat_cleanup import (
    is_stale_navigation_callback,
    reset_navigation_session,
    track_bot_message,
)
from tests.test_sprint45_chat_cleanup import FakeBot, FakeMessage
from tests.utils import session_scope


class MissingMessageBot(FakeBot):
    async def delete_message(self, chat_id: int, message_id: int) -> None:
        if message_id in self.fail_ids:
            raise RuntimeError("Bad Request: message to delete not found")
        await super().delete_message(chat_id, message_id)


def _screen(text: str = "Home") -> Screen:
    return Screen(text=text, reply_markup=None)


def test_start_cleanup_deletes_every_temporary_label_and_preserves_every_persistent_label() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        expected_deleted: list[tuple[int, int]] = []
        message_id = 20
        for label in TEMPORARY_MESSAGE_LABELS:
            track_bot_message(
                session,
                chat_id=10,
                user=owner,
                message_id=message_id,
                message_label=label,
                screen=label,
                active_navigation=label == TEMPORARY_NAVIGATION,
            )
            expected_deleted.append((10, message_id))
            message_id += 1
        for label in PRESERVED_MESSAGE_LABELS:
            track_bot_message(
                session,
                chat_id=10,
                user=owner,
                message_id=message_id,
                message_label=label,
                screen=label,
            )
            message_id += 1

        bot = FakeBot()
        asyncio.run(_cleanup_navigation_messages_on_start(bot, session, user=owner, chat_id=10))

        assert sorted(bot.deleted) == sorted(expected_deleted)
        for record in session.query(BotChatMessage).all():
            if record.message_label in TEMPORARY_MESSAGE_LABELS:
                assert record.deletion_status == "deleted"
                assert record.active_navigation is False
            else:
                assert record.deletion_status == "preserved"


def test_unknown_preserve_is_never_deleted_by_start_cleanup() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        track_bot_message(
            session,
            chat_id=10,
            user=owner,
            message_id=30,
            message_label=UNKNOWN_PRESERVE,
            screen="unknown",
        )

        bot = FakeBot()
        asyncio.run(_cleanup_navigation_messages_on_start(bot, session, user=owner, chat_id=10))

        record = session.query(BotChatMessage).filter_by(message_id=30).one()
        assert bot.deleted == []
        assert record.deletion_status == "preserved"


def test_start_cleanup_records_statuses_and_does_not_count_missing_message_as_failure() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        track_bot_message(
            session,
            chat_id=10,
            user=owner,
            message_id=40,
            message_label=TEMPORARY_NAVIGATION,
            screen="menu",
        )
        track_bot_message(
            session,
            chat_id=10,
            user=owner,
            message_id=41,
            message_label=TEMPORARY_STATUS,
            screen="selftest",
            active_navigation=False,
        )

        asyncio.run(_cleanup_navigation_messages_on_start(MissingMessageBot(fail_ids={41}), session, user=owner, chat_id=10))

        missing = session.query(BotChatMessage).filter_by(message_id=41).one()
        run = session.query(ChatCleanupRun).one()
        assert missing.deletion_status == "already_missing"
        assert run.attempted_count == 2
        assert run.deleted_count == 1
        assert run.failed_count == 0


def test_start_cleanup_resets_to_one_active_navigation_session() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        other = get_or_create_telegram_user(session, telegram_user_id=2, owner_telegram_id=1)
        track_bot_message(session, chat_id=10, user=owner, message_id=50, screen="menu")
        track_bot_message(session, chat_id=10, user=other, message_id=51, screen="help")

        navigation_version = asyncio.run(_cleanup_navigation_messages_on_start(FakeBot(), session, user=owner, chat_id=10))
        asyncio.run(
            _send_tracked_navigation_message(
                FakeMessage(10),
                session,
                user=owner,
                screen=_screen(),
                page="menu",
                navigation_version=navigation_version,
            )
        )

        active_records = session.query(BotChatMessage).filter_by(chat_id=10, active_navigation=True).all()
        assert len(active_records) == 1
        assert active_records[0].message_id == 1000
        assert active_records[0].navigation_version == navigation_version


def test_prior_navigation_version_is_rejected_as_stale_after_reset() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        old = track_bot_message(session, chat_id=10, user=owner, message_id=60, screen="menu")
        new_version = reset_navigation_session(session, chat_id=10, user=None)
        fresh = track_bot_message(
            session,
            chat_id=10,
            user=owner,
            message_id=61,
            message_label=TEMPORARY_NAVIGATION,
            screen="menu",
            navigation_version=new_version,
        )

        assert old.navigation_version != fresh.navigation_version
        assert is_stale_navigation_callback(session, chat_id=10, user=owner, message_id=60) is True
        assert is_stale_navigation_callback(session, chat_id=10, user=owner, message_id=61) is False


def test_concurrent_start_reuses_cleanup_batch() -> None:
    async def scenario():
        with session_scope() as session:
            owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
            from app.bot import runner

            lock = await runner.CALLBACK_LOCKS.acquire_cleanup_lock(chat_id=10, ttl_seconds=5)
            assert lock is not None
            try:
                await _cleanup_navigation_messages_on_start(FakeBot(), session, user=owner, chat_id=10)
                run = session.query(ChatCleanupRun).one()
                assert run.status == "reused"
                assert run.concurrency_reuse_count == 1
            finally:
                await runner.CALLBACK_LOCKS.release(lock)

    asyncio.run(scenario())


def test_canonical_message_labels_are_the_only_tracking_labels() -> None:
    assert set(MESSAGE_LABELS) == {
        "temporary_navigation",
        "temporary_help",
        "temporary_status",
        "temporary_error",
        "persistent_alert",
        "persistent_report",
        "persistent_export",
        "persistent_approval",
        "persistent_incident",
        "persistent_delivery",
        "unknown_preserve",
    }


def test_chat_cleanup_failures_surface_in_observability_from_tracking_schema() -> None:
    with session_scope() as session:
        session.add(
            ChatCleanupRun(
                cleanup_run_id="cleanup-test",
                chat_id=10,
                status="completed",
                started_at=datetime.now(UTC),
                completed_at=datetime.now(UTC),
                attempted_count=4,
                deleted_count=1,
                preserved_count=2,
                failed_count=3,
            )
        )
        session.flush()

        summary = production_observability_summary(session)

        assert summary["chat_cleanup_failed_count"] == 3
        assert "Chat Cleanup: 3 recent deletion failure(s)." in summary["observability_current_issues"]


def test_command_status_screens_are_tracked_as_temporary_messages() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        asyncio.run(
            _send_tracked_temporary_message(
                FakeMessage(10),
                session,
                user=owner,
                text="Fortuna Bot Status",
                reply_markup=None,
                screen="botstatus",
            )
        )

        record = session.query(BotChatMessage).filter_by(message_id=1000).one()
        assert record.message_label == TEMPORARY_STATUS
        assert record.screen == "botstatus"
        assert record.deletion_status == "active"


def test_start_cleanup_uses_bounded_foreground_batch() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        for index in range(5):
            track_bot_message(
                session,
                chat_id=10,
                user=owner,
                message_id=300 + index,
                message_label=TEMPORARY_NAVIGATION,
                screen="menu",
            )

        bot = FakeBot()
        asyncio.run(
            _cleanup_navigation_messages_on_start(
                bot,
                session,
                user=owner,
                chat_id=10,
                cleanup_limit=2,
                time_budget_seconds=10,
            )
        )

        run = session.query(ChatCleanupRun).one()
        assert run.attempted_count == 2
        assert len(bot.deleted) == 2
        assert session.query(BotChatMessage).filter_by(chat_id=10, deletion_status="active").count() == 3
