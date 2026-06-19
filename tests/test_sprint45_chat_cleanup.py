import asyncio

from aiogram.types import InlineKeyboardMarkup

from app.bot.runner import (
    _cleanup_navigation_messages_on_start,
    _edit_or_send_callback_screen,
    _send_tracked_navigation_message,
)
from app.bot.navigation import screen_for_page
from app.bot.screens.formatting import Screen
from app.models.chat import BotChatMessage
from app.services.auth import setup_owner_if_needed
from app.services.permissions import PermissionPrincipal, RoleName
from app.services.chat_cleanup import (
    PERSISTENT_ALERT,
    TEMPORARY_ERROR,
    TEMPORARY_NAVIGATION,
    set_chat_cleanup_enabled,
    track_bot_message,
)
from tests.utils import session_scope


class FakeChat:
    def __init__(self, chat_id: int) -> None:
        self.id = chat_id


class FakeSentMessage:
    def __init__(self, chat_id: int, message_id: int) -> None:
        self.chat = FakeChat(chat_id)
        self.message_id = message_id


class FakeBot:
    def __init__(self, *, fail_ids: set[int] | None = None) -> None:
        self.deleted: list[tuple[int, int]] = []
        self.fail_ids = fail_ids or set()

    async def delete_message(self, chat_id: int, message_id: int) -> None:
        if message_id in self.fail_ids:
            raise RuntimeError("telegram refused delete")
        self.deleted.append((chat_id, message_id))


class FakeMessage:
    def __init__(
        self,
        chat_id: int,
        message_id: int = 100,
        *,
        edit_error: Exception | None = None,
        answer_error: Exception | None = None,
    ) -> None:
        self.chat = FakeChat(chat_id)
        self.message_id = message_id
        self.edit_error = edit_error
        self.answer_error = answer_error
        self.sent: list[FakeSentMessage] = []
        self.edited: list[str] = []

    async def answer(self, text: str, reply_markup=None):
        if self.answer_error is not None:
            raise self.answer_error
        sent = FakeSentMessage(self.chat.id, 1000 + len(self.sent))
        self.sent.append(sent)
        return sent

    async def edit_text(self, text: str, reply_markup=None):
        if self.edit_error is not None:
            raise self.edit_error
        self.edited.append(text)


class FakeCallback:
    def __init__(self, message: FakeMessage) -> None:
        self.message = message
        self.answered: list[tuple[str | None, bool]] = []

    async def answer(self, text: str | None = None, show_alert: bool = False):
        self.answered.append((text, show_alert))


def _screen(text: str = "Home") -> Screen:
    return Screen(text=text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[]))


def test_start_cleanup_deletes_only_temporary_navigation_messages() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        track_bot_message(
            session,
            chat_id=10,
            user=owner,
            message_id=11,
            message_label=TEMPORARY_NAVIGATION,
            screen="menu",
        )
        track_bot_message(
            session,
            chat_id=10,
            user=owner,
            message_id=12,
            message_label=PERSISTENT_ALERT,
            screen="creator_alert",
        )

        bot = FakeBot()
        asyncio.run(_cleanup_navigation_messages_on_start(bot, session, user=owner, chat_id=10))

        assert bot.deleted == [(10, 11)]
        temp = session.query(BotChatMessage).filter_by(message_id=11).one()
        alert = session.query(BotChatMessage).filter_by(message_id=12).one()
        assert temp.deletion_status == "deleted"
        assert temp.active_navigation is False
        assert alert.deletion_status == "preserved"
        assert alert.active_navigation is False


def test_start_cleanup_failure_does_not_block_fresh_home_tracking() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        track_bot_message(
            session,
            chat_id=10,
            user=owner,
            message_id=11,
            message_label=TEMPORARY_NAVIGATION,
            screen="menu",
        )

        asyncio.run(_cleanup_navigation_messages_on_start(FakeBot(fail_ids={11}), session, user=owner, chat_id=10))
        asyncio.run(_send_tracked_navigation_message(FakeMessage(10), session, user=owner, screen=_screen(), page="menu"))

        failed = session.query(BotChatMessage).filter_by(message_id=11).one()
        fresh = session.query(BotChatMessage).filter_by(message_id=1000).one()
        assert failed.deletion_status == "failed"
        assert fresh.message_label == TEMPORARY_NAVIGATION
        assert fresh.screen == "menu"
        assert fresh.active_navigation is True


def test_chat_cleanup_respects_keep_menu_history_setting() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        track_bot_message(
            session,
            chat_id=10,
            user=owner,
            message_id=11,
            message_label=TEMPORARY_NAVIGATION,
            screen="menu",
        )
        set_chat_cleanup_enabled(session, user=owner, chat_id=10, enabled=False)

        bot = FakeBot()
        asyncio.run(_cleanup_navigation_messages_on_start(bot, session, user=owner, chat_id=10))

        assert bot.deleted == []
        record = session.query(BotChatMessage).filter_by(message_id=11).one()
        assert record.deletion_status == "active"
        assert record.active_navigation is False


def test_callback_navigation_updates_active_message_tracking() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        callback = FakeCallback(FakeMessage(10, message_id=22))

        asyncio.run(
            _edit_or_send_callback_screen(
                callback,
                _screen("Proxy Vault"),
                session=session,
                user=owner,
                page="proxies",
            )
        )

        record = session.query(BotChatMessage).filter_by(chat_id=10, message_id=22).one()
        assert callback.message.edited == ["Proxy Vault"]
        assert record.message_label == TEMPORARY_NAVIGATION
        assert record.screen == "proxies"
        assert record.active_navigation is True


def test_duplicate_callback_message_not_modified_is_harmless() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        callback = FakeCallback(
            FakeMessage(10, message_id=24, edit_error=RuntimeError("Bad Request: message is not modified"))
        )

        asyncio.run(
            _edit_or_send_callback_screen(
                callback,
                _screen("Proxy Vault"),
                session=session,
                user=owner,
                page="proxies",
            )
        )

        assert callback.message.sent == []
        assert callback.answered == []
        assert session.query(BotChatMessage).filter_by(message_id=24).count() == 0


def test_stale_callback_edit_sends_fresh_screen() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        callback = FakeCallback(
            FakeMessage(10, message_id=25, edit_error=RuntimeError("Bad Request: message to edit not found"))
        )

        asyncio.run(
            _edit_or_send_callback_screen(
                callback,
                _screen("Recovery Center"),
                session=session,
                user=owner,
                page="recovery_center",
            )
        )

        assert callback.message.sent
        record = session.query(BotChatMessage).filter_by(chat_id=10, message_id=1000).one()
        assert record.message_label == TEMPORARY_NAVIGATION
        assert record.screen == "recovery_center"


def test_callback_edit_and_fallback_send_failure_does_not_raise() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        callback = FakeCallback(
            FakeMessage(
                10,
                message_id=26,
                edit_error=RuntimeError("Bad Request: message can't be edited"),
                answer_error=RuntimeError("telegram send failed"),
            )
        )

        asyncio.run(
            _edit_or_send_callback_screen(
                callback,
                _screen("Recovery Center"),
                session=session,
                user=owner,
                page="recovery_center",
            )
        )

        assert callback.answered == [("Fortuna had trouble updating that message. Use /start to refresh.", True)]


def test_error_fallback_is_temporary_and_cleanup_candidate() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        callback = FakeCallback(FakeMessage(10, message_id=23))

        asyncio.run(
            _edit_or_send_callback_screen(
                callback,
                _screen("Fortuna encountered a problem loading this screen."),
                session=session,
                user=owner,
                page="proxy:1",
                message_label=TEMPORARY_ERROR,
            )
        )
        bot = FakeBot()
        asyncio.run(_cleanup_navigation_messages_on_start(bot, session, user=owner, chat_id=10))

        record = session.query(BotChatMessage).filter_by(message_id=23).one()
        assert record.message_label == TEMPORARY_ERROR
        assert bot.deleted == [(10, 23)]
        assert record.deletion_status == "deleted"
        assert record.active_navigation is False


def test_chat_cleanup_settings_route_and_toggle_render() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        principal = PermissionPrincipal(telegram_id=owner.telegram_id, is_owner=True, role=RoleName.OWNER)

        screen = screen_for_page("settings:chat_cleanup", principal, session=session, user=owner, chat_id=10)

        assert "Chat Cleanup" in screen.text
        assert "Clean on /start" in screen.text
        assert "Preserve reports and alerts" in screen.text
        assert "delivery messages are preserved" in screen.text

        toggled = screen_for_page(
            "settings:chat_cleanup:toggle",
            principal,
            session=session,
            user=owner,
            chat_id=10,
        )

        assert "Keep menu history" in toggled.text
