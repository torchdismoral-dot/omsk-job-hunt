from __future__ import annotations

import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramNetworkError

from ..config import load_config, load_dotenv
from .handlers import build_router

RETRY_SECONDS = 15.0


async def poll_forever(bot: Bot, dispatcher: Dispatcher, delay: float = RETRY_SECONDS) -> None:
    while True:
        try:
            await dispatcher.start_polling(bot)
            return
        except TelegramNetworkError as error:
            logging.warning("Telegram недоступен (%s), повтор через %.0f с", error, delay)
            await asyncio.sleep(delay)


async def main() -> None:
    load_dotenv()
    logging.basicConfig(level=logging.INFO)
    settings = load_config(os.environ.get("JOBHUNT_CONFIG", "config.yaml"))
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise SystemExit("BOT_TOKEN не задан: положи его в .env")
    bot = Bot(token=token, default=DefaultBotProperties(parse_mode="HTML"))
    dispatcher = Dispatcher()
    dispatcher.include_router(
        build_router(settings, os.environ.get("JOBHUNT_DB", "jobhunt.db"))
    )
    await poll_forever(bot, dispatcher)


if __name__ == "__main__":
    asyncio.run(main())
