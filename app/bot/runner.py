import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import Message

from app.bot.menu import main_menu
from app.core.config import settings
from app.core.logging import configure_logging
from app.services.permissions import PermissionPrincipal, require_owner

logger = logging.getLogger(__name__)
dp = Dispatcher()


@dp.message(CommandStart())
async def start(message: Message) -> None:
    principal = PermissionPrincipal(
        telegram_id=message.from_user.id if message.from_user else 0,
        is_owner=False,
    )
    try:
        require_owner(principal, settings.owner_telegram_id)
        await message.answer("Owner setup ready.", reply_markup=main_menu())
    except PermissionError:
        await message.answer("Access pending owner approval.")


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
