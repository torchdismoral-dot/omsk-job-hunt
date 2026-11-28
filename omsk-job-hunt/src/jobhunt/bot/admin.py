from __future__ import annotations

import asyncio
import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from ..config import Settings
from ..db import DB
from ..pipeline import refresh
from .messages import NO_ACCESS_TEXT, REFRESH_FAILED_TEXT, REFRESH_START_TEXT

log = logging.getLogger(__name__)


def summary_text(stats: dict) -> str:
    """Итог сбора. Строку про hh показываем только если он реально участвовал."""
    text = (
        f"Сбор завершен! Добавлено новых вакансий: {stats['fresh']}. "
        f"Всего в базе: {stats['total']}"
    )
    if stats.get("hh_fetched") or stats.get("hh_error"):
        text += f"\nСобрано с hh.ru: {stats.get('hh_fetched', 0)}"
    if stats.get("hh_error"):
        text += f"\n⚠️ {stats['hh_error']}"
    return text


def build_admin_router(settings: Settings, db_path: str) -> Router:
    router = Router()

    @router.message(Command("refresh"))
    async def refresh_command(message: Message) -> None:
        if settings.admin_id is None or message.from_user.id != settings.admin_id:
            log.warning("сбор по /refresh отклонён: chat=%s", message.from_user.id)
            await message.answer(NO_ACCESS_TEXT)
            return

        await message.answer(REFRESH_START_TEXT)

        def run_refresh() -> dict:
            # sqlite3-соединение живёт в том же потоке, где и работа с ним
            db = DB(db_path)
            try:
                return refresh(settings, db)
            finally:
                db.close()

        try:
            stats = await asyncio.to_thread(run_refresh)
        except Exception:
            log.exception("ручной сбор вакансий не удался")
            await message.answer(REFRESH_FAILED_TEXT)
            return

        await message.answer(summary_text(stats))

    return router
