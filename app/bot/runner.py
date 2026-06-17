import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram import F
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message

from app.bot.navigation import screen_for_page
from app.bot.screens import render_access_pending, render_disabled, render_main_menu
from app.core.config import settings
from app.core.logging import configure_logging
from app.db.session import SessionLocal
from app.models.user import User
from app.services.auth import (
    USER_STATUS_DISABLED,
    USER_STATUS_PENDING,
    get_or_create_telegram_user,
    setup_owner_if_needed,
)
from app.services.permissions import PermissionPrincipal, RoleName, require_owner

logger = logging.getLogger(__name__)
dp = Dispatcher()


def _principal_from_user(user: User) -> PermissionPrincipal:
    role = RoleName.OWNER if user.is_owner else RoleName.VIEWER
    return PermissionPrincipal(telegram_id=user.telegram_id, is_owner=user.is_owner, role=role)


def _username_from_message_user(user) -> str | None:
    return user.username if user and user.username else None


@dp.message(CommandStart())
async def start(message: Message) -> None:
    if message.from_user is None or SessionLocal is None:
        await message.answer("Access pending owner approval.")
        return

    with SessionLocal() as session:
        telegram_id = message.from_user.id
        if telegram_id == settings.owner_telegram_id:
            user = setup_owner_if_needed(
                session,
                telegram_user_id=telegram_id,
                username=_username_from_message_user(message.from_user),
                owner_telegram_id=settings.owner_telegram_id,
            )
            session.commit()
            principal = _principal_from_user(user)
            require_owner(principal, settings.owner_telegram_id)
            screen = render_main_menu()
            await message.answer(screen.text, reply_markup=screen.reply_markup)
            return

        user = get_or_create_telegram_user(
            session,
            telegram_user_id=telegram_id,
            username=_username_from_message_user(message.from_user),
            owner_telegram_id=settings.owner_telegram_id,
        )
        session.commit()

    if user.status == USER_STATUS_DISABLED:
        screen = render_disabled()
        await message.answer(screen.text, reply_markup=screen.reply_markup)
    else:
        screen = render_access_pending()
        await message.answer(screen.text, reply_markup=screen.reply_markup)


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
        user = get_or_create_telegram_user(
            session,
            telegram_user_id=callback.from_user.id,
            username=_username_from_message_user(callback.from_user),
            owner_telegram_id=settings.owner_telegram_id,
        )
        principal = _principal_from_user(user)
        if user.status == USER_STATUS_DISABLED:
            screen = render_disabled()
            await callback.message.edit_text(screen.text, reply_markup=screen.reply_markup)
            await callback.answer("Access disabled.", show_alert=True)
            session.commit()
            return
        if user.status == USER_STATUS_PENDING:
            screen = render_access_pending()
            await callback.message.edit_text(screen.text, reply_markup=screen.reply_markup)
            await callback.answer("Access pending.", show_alert=True)
            session.commit()
            return
        try:
            screen = screen_for_page(page, principal, session=session, user=user)
            await callback.message.edit_text(screen.text, reply_markup=screen.reply_markup)
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
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
