import asyncio
import logging
from datetime import UTC, datetime

from aiogram import Bot, Dispatcher
from aiogram import F
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message

from app.bot.navigation import screen_for_page
from app.bot.screens import (
    render_access_pending,
    render_account_detail_page,
    render_denied,
    render_disabled,
    render_main_menu,
)
from app.core.config import settings
from app.core.logging import configure_logging
from app.db.migrations import run_migrations
from app.db.session import SessionLocal
from app.models.account import AccountAuthSession
from app.models.user import User
from app.services.auth import (
    USER_STATUS_DISABLED,
    USER_STATUS_DENIED,
    USER_STATUS_PENDING,
    audit_action,
    get_or_create_telegram_user,
    mask_telegram_id,
    setup_owner_if_needed,
)
from app.services.accounts import (
    create_account,
    get_account,
    latest_waiting_auth_session,
    submit_verification_code,
)
from app.services.permissions import PermissionPrincipal, RoleName, require_owner
from app.services.model_brands import get_model_brand
from app.services.heartbeats import record_heartbeat
from app.services.notifications import (
    create_delivery_attempt,
    decrypt_target_chat_id,
    get_notification_target,
    mark_delivery_failed,
    mark_delivery_sent,
    mark_delivery_skipped,
)

logger = logging.getLogger(__name__)
dp = Dispatcher()

PENDING_ACCOUNT_CREATES: dict[int, dict[str, int | str]] = {}
PENDING_AUTH_CODES: dict[int, int] = {}


def _principal_from_user(user: User) -> PermissionPrincipal:
    role = RoleName.OWNER if user.is_owner else RoleName.VIEWER
    return PermissionPrincipal(telegram_id=user.telegram_id, is_owner=user.is_owner, role=role)


def _username_from_message_user(user) -> str | None:
    return user.username if user and user.username else None


def _display_name_from_message_user(user) -> str | None:
    if user is None:
        return None
    parts = [getattr(user, "first_name", None), getattr(user, "last_name", None)]
    return " ".join(part for part in parts if part) or getattr(user, "username", None)


def _parse_account_input(text: str) -> tuple[str, str | None]:
    if "|" in text:
        username, display_name = [part.strip() for part in text.split("|", 1)]
        return username.lstrip("@"), display_name or None
    clean = text.strip().lstrip("@")
    return clean, clean


def _set_pending_callback_state(telegram_id: int, page: str, session, user: User) -> None:
    PENDING_ACCOUNT_CREATES.pop(telegram_id, None)
    PENDING_AUTH_CODES.pop(telegram_id, None)
    parts = page.split(":")
    if len(parts) >= 6 and parts[:3] == ["accounts", "add", "model"] and parts[3].isdigit() and parts[4] == "platform":
        PENDING_ACCOUNT_CREATES[telegram_id] = {"model_id": int(parts[3]), "platform": parts[5]}
        return
    if (
        len(parts) >= 4
        and parts[0] == "account"
        and parts[1].isdigit()
        and parts[2] == "auth"
        and parts[3] in {"start", "enter"}
    ):
        account = get_account(session, int(parts[1]))
        if account is None:
            return
        auth_session = latest_waiting_auth_session(session, account.id)
        if auth_session is not None:
            PENDING_AUTH_CODES[telegram_id] = auth_session.id


def _notification_target_id_for_send_test(page: str) -> int | None:
    parts = page.split(":")
    if len(parts) >= 3 and parts[0] == "notification_target" and parts[1].isdigit() and parts[2] == "send_test":
        return int(parts[1])
    return None


@dp.message(CommandStart())
async def start(message: Message) -> None:
    if message.from_user is None or SessionLocal is None:
        await message.answer("Access pending owner approval.")
        return

    with SessionLocal() as session:
        telegram_id = message.from_user.id
        record_heartbeat(session, service_name="bot", status="healthy", metadata={"source": "telegram_start"})
        if telegram_id == settings.owner_telegram_id:
            user = setup_owner_if_needed(
                session,
                telegram_user_id=telegram_id,
                display_name=_display_name_from_message_user(message.from_user),
                username=_username_from_message_user(message.from_user),
                owner_telegram_id=settings.owner_telegram_id,
            )
            user.last_seen = datetime.now(UTC)
            session.commit()
            principal = _principal_from_user(user)
            require_owner(principal, settings.owner_telegram_id)
            screen = render_main_menu()
            await message.answer(screen.text, reply_markup=screen.reply_markup)
            return

        user = get_or_create_telegram_user(
            session,
            telegram_user_id=telegram_id,
            display_name=_display_name_from_message_user(message.from_user),
            username=_username_from_message_user(message.from_user),
            owner_telegram_id=settings.owner_telegram_id,
        )
        user.last_seen = datetime.now(UTC)
        session.commit()

    if user.status == USER_STATUS_DISABLED:
        screen = render_disabled()
        await message.answer(screen.text, reply_markup=screen.reply_markup)
    elif user.status == USER_STATUS_DENIED:
        screen = render_denied()
        await message.answer(screen.text, reply_markup=screen.reply_markup)
    else:
        screen = render_access_pending()
        await message.answer(screen.text, reply_markup=screen.reply_markup)


@dp.message(F.text)
async def text_input(message: Message) -> None:
    if message.from_user is None or SessionLocal is None or message.text is None:
        return

    telegram_id = message.from_user.id
    with SessionLocal() as session:
        record_heartbeat(session, service_name="bot", status="healthy", metadata={"source": "telegram_text"})
        user = get_or_create_telegram_user(
            session,
            telegram_user_id=telegram_id,
            display_name=_display_name_from_message_user(message.from_user),
            username=_username_from_message_user(message.from_user),
            owner_telegram_id=settings.owner_telegram_id,
        )
        if user.status in {USER_STATUS_DISABLED, USER_STATUS_DENIED, USER_STATUS_PENDING}:
            session.commit()
            return

        pending_account = PENDING_ACCOUNT_CREATES.pop(telegram_id, None)
        if pending_account is not None:
            username, display_name = _parse_account_input(message.text)
            model_brand = get_model_brand(session, int(pending_account["model_id"]))
            if model_brand is None:
                await message.answer("Model not found. Start Add Account again.")
                session.commit()
                return
            try:
                account = create_account(
                    session,
                    model_brand=model_brand,
                    platform=str(pending_account["platform"]),
                    username=username,
                    display_name=display_name,
                    actor=user,
                )
            except (PermissionError, ValueError):
                await message.answer("Unable to create account.")
                session.commit()
                return
            screen = render_account_detail_page(session, account.id)
            await message.answer(screen.text, reply_markup=screen.reply_markup)
            session.commit()
            return

        pending_auth_session_id = PENDING_AUTH_CODES.pop(telegram_id, None)
        if pending_auth_session_id is not None:
            auth_session = session.get(AccountAuthSession, pending_auth_session_id)
            if auth_session is None:
                await message.answer("Auth session expired or not found.")
                session.commit()
                return
            submitted_code = message.text.strip()
            try:
                submit_verification_code(
                    session,
                    auth_session,
                    code=submitted_code,
                    code_type="authenticator",
                    actor=user,
                )
                submitted_code = ""
                try:
                    await message.delete()
                except Exception:
                    logger.warning("Unable to delete verification code message")
                account_id = auth_session.account_id
                screen = render_account_detail_page(session, account_id)
                await message.answer("Verification code received securely.")
                await message.answer(screen.text, reply_markup=screen.reply_markup)
            except (PermissionError, ValueError):
                submitted_code = ""
                await message.answer("Unable to submit verification code.")
            session.commit()
            return


@dp.callback_query(F.data.startswith("nav:"))
async def navigate(callback: CallbackQuery) -> None:
    if callback.message is None:
        await callback.answer()
        return

    page = callback.data.removeprefix("nav:") if callback.data else "menu"
    if SessionLocal is None:
        await callback.answer("Database is not configured.", show_alert=True)
        return

    with SessionLocal() as session:
        record_heartbeat(session, service_name="bot", status="healthy", metadata={"source": "telegram_callback"})
        user = get_or_create_telegram_user(
            session,
            telegram_user_id=callback.from_user.id,
            display_name=_display_name_from_message_user(callback.from_user),
            username=_username_from_message_user(callback.from_user),
            owner_telegram_id=settings.owner_telegram_id,
        )
        user.last_seen = datetime.now(UTC)
        principal = _principal_from_user(user)
        if user.status == USER_STATUS_DISABLED:
            audit_action(
                session,
                actor=user,
                action="access.denied",
                resource_type="telegram_page",
                resource_id=page,
                status="denied",
                details={"reason": "disabled", "telegram_id_masked": mask_telegram_id(user.telegram_id)},
            )
            screen = render_disabled()
            await callback.message.edit_text(screen.text, reply_markup=screen.reply_markup)
            await callback.answer("Access disabled.", show_alert=True)
            session.commit()
            return
        if user.status == USER_STATUS_DENIED:
            audit_action(
                session,
                actor=user,
                action="access.denied",
                resource_type="telegram_page",
                resource_id=page,
                status="denied",
                details={"reason": "denied", "telegram_id_masked": mask_telegram_id(user.telegram_id)},
            )
            screen = render_denied()
            await callback.message.edit_text(screen.text, reply_markup=screen.reply_markup)
            await callback.answer("Access denied.", show_alert=True)
            session.commit()
            return
        if user.status == USER_STATUS_PENDING:
            audit_action(
                session,
                actor=user,
                action="access.denied",
                resource_type="telegram_page",
                resource_id=page,
                status="denied",
                details={"reason": "pending", "telegram_id_masked": mask_telegram_id(user.telegram_id)},
            )
            screen = render_access_pending()
            await callback.message.edit_text(screen.text, reply_markup=screen.reply_markup)
            await callback.answer("Access pending.", show_alert=True)
            session.commit()
            return
        try:
            chat_id = callback.message.chat.id
            chat_title = getattr(callback.message.chat, "title", None)
            screen = screen_for_page(
                page,
                principal,
                session=session,
                user=user,
                chat_id=chat_id,
                chat_title=chat_title,
            )
            _set_pending_callback_state(callback.from_user.id, page, session, user)
            await callback.message.edit_text(screen.text, reply_markup=screen.reply_markup)
            target_id = _notification_target_id_for_send_test(page)
            if target_id is not None:
                target = get_notification_target(session, target_id)
                raw_chat_id = decrypt_target_chat_id(target) if target else None
                attempt = None
                if target is not None:
                    attempt = create_delivery_attempt(
                        session,
                        target,
                        event_type="notification.test",
                        actor=user,
                        metadata={"source": "telegram_test"},
                    )
                if target is None or not target.is_active or target.purpose != "testing" or raw_chat_id is None:
                    if attempt is not None:
                        mark_delivery_skipped(session, attempt, actor=user, reason="test target not eligible")
                    await callback.answer("Test sends require an active testing target.", show_alert=True)
                    session.commit()
                    return
                try:
                    await callback.bot.send_message(int(raw_chat_id), "Agency OS test notification.")
                    if attempt is not None:
                        mark_delivery_sent(session, attempt, actor=user)
                except Exception:
                    if attempt is not None:
                        mark_delivery_failed(session, attempt, actor=user, error_message="telegram_send_failed")
                    logger.warning("Unable to send test notification to configured target")
            await callback.answer()
            session.commit()
        except PermissionError:
            session.commit()
            await callback.answer("You do not have permission to open this page.", show_alert=True)


async def main() -> None:
    configure_logging()
    token = settings.telegram_bot_token.get_secret_value()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")
    bot = Bot(token=token)
    logger.info("Starting Telegram bot")
    if SessionLocal is not None:
        run_migrations()
        with SessionLocal() as session:
            record_heartbeat(session, service_name="bot", status="healthy", metadata={"source": "startup"})
            session.commit()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
