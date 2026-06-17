import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram import F
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message

from app.bot.navigation import screen_for_page
from app.bot.screens import render_main_menu
from app.core.config import settings
from app.core.logging import configure_logging
from app.services.permissions import PermissionPrincipal, RoleName, require_owner

logger = logging.getLogger(__name__)
dp = Dispatcher()


@dp.message(CommandStart())
async def start(message: Message) -> None:
    principal = PermissionPrincipal(
        telegram_id=message.from_user.id if message.from_user else 0,
        is_owner=message.from_user.id == settings.owner_telegram_id if message.from_user else False,
        role=RoleName.OWNER if message.from_user and message.from_user.id == settings.owner_telegram_id else RoleName.VIEWER,
    )
    try:
        require_owner(principal, settings.owner_telegram_id)
        screen = render_main_menu()
        await message.answer(screen.text, reply_markup=screen.reply_markup)
    except PermissionError:
        await message.answer("Access pending owner approval.")


@dp.callback_query(F.data.startswith("nav:"))
async def navigate(callback: CallbackQuery) -> None:
    if callback.message is None:
        await callback.answer()
        return

    page = callback.data.removeprefix("nav:") if callback.data else "menu"
    principal = PermissionPrincipal(
        telegram_id=callback.from_user.id,
        is_owner=callback.from_user.id == settings.owner_telegram_id,
        role=RoleName.OWNER if callback.from_user.id == settings.owner_telegram_id else RoleName.VIEWER,
    )
    try:
        screen = screen_for_page(page, principal)
        await callback.message.edit_text(screen.text, reply_markup=screen.reply_markup)
        await callback.answer()
    except PermissionError:
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
