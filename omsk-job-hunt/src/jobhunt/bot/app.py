from __future__ import annotations

import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta

from aiogram import BaseMiddleware, Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramNetworkError
from aiogram.types import Update
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from ..config import Settings, load_config, load_dotenv
from ..db import DB, persistence_warning
from ..pipeline import refresh
from .digest import send_digests
from .handlers import build_router
from .storage import SQLiteStorage

RETRY_SECONDS = 15.0
DIGEST_MINUTE = 5
log = logging.getLogger(__name__)

# Одна коллекция за раз: автосбор на старте, планировщик и /refresh не должны
# выкачивать площадки параллельно.
_refresh_lock = asyncio.Lock()


def setup_logging(path: str | None = None) -> None:
    """stdout — основной поток логов: PaaS (Amvera, Docker) собирает их оттуда.

    Файл пишем дополнительно и только если он открывается; на read-only ФС
    это не должно ронять бота. Пустая строка в JOBHUNT_LOG_FILE отключает файл.
    """
    if path is None:
        path = os.environ.get("JOBHUNT_LOG_FILE", "bot.log")
    handlers: list[logging.Handler] = []
    # pythonw (Планировщик Windows) оставляет оба потока пустыми.
    stream = sys.stdout if sys.stdout is not None else sys.stderr
    if stream is not None:
        handlers.append(logging.StreamHandler(stream))
    if path:
        try:
            handlers.append(logging.FileHandler(path, encoding="utf-8"))
        except OSError as error:
            logging.getLogger(__name__).warning(
                "файл лога %s недоступен (%s), пишу только в stdout", path, error
            )
    if not handlers:
        handlers.append(logging.NullHandler())
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
        force=True,
    )


def next_at(hour: int, minute: int, now: datetime | None = None) -> datetime:
    """Ближайшее наступление hour:minute (сегодня или завтра)."""
    now = now or datetime.now().astimezone()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target


def describe_update(update: Update) -> str:
    if update.message is not None:
        message = update.message
        return f"message chat={message.chat.id} text={message.text!r}"
    if update.callback_query is not None:
        query = update.callback_query
        return f"callback chat={query.message.chat.id if query.message else query.from_user.id} data={query.data!r}"
    return f"update type={update.event_type}"


class LogUpdates(BaseMiddleware):
    async def __call__(self, handler, event: Update, data):
        log.info("входящее: %s", describe_update(event))
        return await handler(event, data)


async def poll_forever(bot: Bot, dispatcher: Dispatcher, delay: float = RETRY_SECONDS) -> None:
    while True:
        try:
            await dispatcher.start_polling(bot)
            return
        except TelegramNetworkError as error:
            logging.warning("Telegram недоступен (%s), повтор через %.0f с", error, delay)
            await asyncio.sleep(delay)


async def refresh_job(settings: Settings, db_path: str, refresh_fn=refresh) -> dict | None:
    """Ежедневное обновление базы вакансий."""

    def run_refresh():
        # SQLite-соединение живёт в том же потоке, где и работа с ним
        db = DB(db_path)
        try:
            return refresh_fn(settings, db)
        finally:
            db.close()

    try:
        async with _refresh_lock:
            stats = await asyncio.to_thread(run_refresh)
        log.info("база обновлена: %s", stats)
        return stats
    except Exception:
        log.exception("обновление базы не удалось")
        return None


BOOTSTRAP_DELAY = 10.0
BOOTSTRAP_ATTEMPTS = 3
BOOTSTRAP_RETRY_DELAY = 60.0


async def ensure_database(
    settings: Settings,
    db_path: str,
    refresh_fn=refresh,
    delay: float = BOOTSTRAP_DELAY,
    attempts: int = BOOTSTRAP_ATTEMPTS,
    retry_delay: float = BOOTSTRAP_RETRY_DELAY,
) -> dict | None:
    """Пустая база после старта или redeploy — наполняем сразу, не ждём 09:00.

    Иначе первые сутки после деплоя бот показывал бы «пусто» всем подряд.
    Повторы нужны потому, что источники могут отказать выборочно: пустой
    результат первого прогона обычно значит именно это, а не отсутствие
    вакансий.
    """

    def count() -> int:
        db = DB(db_path)
        try:
            return db.count()
        finally:
            db.close()

    total = await asyncio.to_thread(count)
    if total:
        log.info("вакансий в базе: %d — немедленный сбор не нужен", total)
        return None
    log.warning("база пуста (%s) — запускаю сбор через %.0f с", db_path, delay)
    await asyncio.sleep(delay)
    stats = None
    for attempt in range(1, attempts + 1):
        stats = await refresh_job(settings, db_path, refresh_fn)
        if stats and stats.get("total"):
            return stats
        if attempt < attempts:
            log.warning(
                "после попытки %d база пуста — повтор через %.0f с", attempt, retry_delay
            )
            await asyncio.sleep(retry_delay)
    return stats


async def digest_job(bot: Bot, settings: Settings, db_path: str, refresh_fn=refresh) -> int:
    """Обновляет базу и рассылает новое. Молчит, если новых нет."""
    await refresh_job(settings, db_path, refresh_fn)
    db = DB(db_path)
    try:
        sent = await send_digests(bot, db, settings)
        log.info("дайджест: отправлено вакансий %s", sent)
        return sent
    finally:
        db.close()


async def main() -> None:
    load_dotenv()
    setup_logging()
    settings = load_config(os.environ.get("JOBHUNT_CONFIG", "config.yaml"))
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise SystemExit("BOT_TOKEN не задан: положи его в .env")
    bot = Bot(token=token, default=DefaultBotProperties(parse_mode="HTML"))
    fsm_path = os.environ.get("JOBHUNT_FSM_DB", "fsm.db")
    dispatcher = Dispatcher(storage=SQLiteStorage(fsm_path))
    dispatcher.update.outer_middleware(LogUpdates())
    db_path = os.environ.get("JOBHUNT_DB", "jobhunt.db")
    log.info("база вакансий: %s", db_path)
    warning = persistence_warning(db_path)
    if warning:
        log.warning(warning)
    dispatcher.include_router(build_router(settings, db_path))

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        refresh_job,
        "cron",
        hour=settings.refresh_hour,
        minute=0,
        args=[settings, db_path],
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        digest_job,
        "interval",
        hours=settings.digest_hours,
        start_date=next_at(settings.refresh_hour, DIGEST_MINUTE),
        args=[bot, settings, db_path],
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
    )
    scheduler.start()
    log.info(
        "обновление базы ежедневно в %02d:00, дайджест каждые %d ч",
        settings.refresh_hour,
        settings.digest_hours,
    )
    background: set[asyncio.Task] = set()
    bootstrap = asyncio.create_task(ensure_database(settings, db_path))
    background.add(bootstrap)
    bootstrap.add_done_callback(background.discard)
    await poll_forever(bot, dispatcher)


if __name__ == "__main__":
    asyncio.run(main())
