from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramNetworkError
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from ..config import Settings, load_config, load_dotenv
from ..db import DB
from ..pipeline import refresh
from .digest import send_digests
from .handlers import build_router

RETRY_SECONDS = 15.0
log = logging.getLogger(__name__)


async def poll_forever(bot: Bot, dispatcher: Dispatcher, delay: float = RETRY_SECONDS) -> None:
    while True:
        try:
            await dispatcher.start_polling(bot)
            return
        except TelegramNetworkError as error:
            logging.warning("Telegram недоступен (%s), повтор через %.0f с", error, delay)
            await asyncio.sleep(delay)


async def digest_job(bot: Bot, settings: Settings, db_path: str, refresh_fn=refresh) -> int:
    """Обновляет базу и рассылает новое подписчикам. Молчит, если новых нет."""

    def run_refresh():
        # SQLite-соединение живёт в том же потоке, где и работа с ним
        db = DB(db_path)
        try:
            return refresh_fn(settings, db)
        finally:
            db.close()

    try:
        stats = await asyncio.to_thread(run_refresh)
        log.info("база обновлена: %s", stats)
    except Exception:
        log.exception("обновление базы не удалось, рассылаю по старой")
    db = DB(db_path)
    try:
        sent = await send_digests(bot, db, settings)
        log.info("дайджест: отправлено вакансий %s", sent)
        return sent
    finally:
        db.close()


async def main() -> None:
    load_dotenv()
    logging.basicConfig(level=logging.INFO)
    settings = load_config(os.environ.get("JOBHUNT_CONFIG", "config.yaml"))
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise SystemExit("BOT_TOKEN не задан: положи его в .env")
    bot = Bot(token=token, default=DefaultBotProperties(parse_mode="HTML"))
    dispatcher = Dispatcher()
    db_path = os.environ.get("JOBHUNT_DB", "jobhunt.db")
    dispatcher.include_router(build_router(settings, db_path))

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        digest_job,
        "interval",
        hours=settings.digest_hours,
        args=[bot, settings, db_path],
        next_run_time=datetime.now(),
        coalesce=True,
        max_instances=1,
    )
    scheduler.start()
    await poll_forever(bot, dispatcher)


if __name__ == "__main__":
    asyncio.run(main())
