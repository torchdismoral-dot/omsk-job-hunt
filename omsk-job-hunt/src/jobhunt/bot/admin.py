from __future__ import annotations

import asyncio
import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from ..config import Settings
from ..db import DB, persistence_warning
from ..pipeline import refresh
from .messages import (
    NO_ACCESS_TEXT,
    REFRESH_FAILED_TEXT,
    REFRESH_START_TEXT,
    STATS_FAILED_TEXT,
)

log = logging.getLogger(__name__)

SOURCE_LABELS = {"superjob": "SuperJob", "trudvsem": "Trudvsem", "hh": "hh.ru"}


def summary_text(stats: dict) -> str:
    """Итог сбора: счётчики по площадкам и предупреждения тех, кто не пустил."""
    text = (
        f"Сбор завершен! Добавлено новых вакансий: {stats['fresh']}. "
        f"Всего в базе: {stats['total']}"
    )
    others = [
        f"{SOURCE_LABELS[name]}: {stats[f'{name}_fetched']}"
        for name in ("superjob", "trudvsem")
        if f"{name}_fetched" in stats
    ]
    if others:
        text += "\nСобрано: " + ", ".join(others)
    if stats.get("hh_fetched") or stats.get("hh_error"):
        text += f"\nСобрано с hh.ru: {stats.get('hh_fetched', 0)}"
    errors = dict(stats.get("errors") or {})
    if stats.get("hh_error"):
        errors.setdefault("hh", stats["hh_error"])
    for error in errors.values():
        text += f"\n⚠️ {error}"
    return text


def collect_stats(db_path: str) -> dict:
    """Снимок состояния базы для /stats. Вызывается вне потока событий."""
    db = DB(db_path)
    try:
        return {
            "db_path": db.path,
            "total": db.count(),
            "by_source": db.count_by_source(),
            "users": db.users_count(),
            "donations": db.donations_total(),
            "last_run": db.last_run(),
        }
    finally:
        db.close()


def stats_text(info: dict) -> str:
    lines = [f"Файл базы: {info['db_path']}"]
    warning = persistence_warning(info["db_path"])
    if warning:
        lines.append(f"⚠️ {warning}")
    lines.append(f"Всего вакансий: {info['total']}")
    by_source = info.get("by_source") or {}
    sources = ", ".join(
        f"{SOURCE_LABELS.get(name, name)}: {count}" for name, count in sorted(by_source.items())
    )
    lines.append(f"По источникам: {sources or 'пусто'}")
    lines.append(f"Пользователей: {info.get('users', 0)}")
    donations = info.get("donations") or (0, 0)
    lines.append(f"Донатов: {donations[0]} на {donations[1]} ₽")
    run = info.get("last_run")
    if run:
        line = (
            f"Последний сбор: {run.get('finished_at')} — "
            f"получено {run.get('fetched')}, новых {run.get('fresh')}"
        )
        if run.get("error"):
            line += f"\n⚠️ {run['error']}"
        lines.append(line)
    else:
        lines.append("Последний сбор: ещё не запускался")
    return "\n".join(lines)


def build_admin_router(settings: Settings, db_path: str) -> Router:
    router = Router()

    def allowed(message: Message) -> bool:
        return settings.admin_id is not None and message.from_user.id == settings.admin_id

    @router.message(Command("refresh"))
    async def refresh_command(message: Message) -> None:
        if not allowed(message):
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
        except Exception as error:
            log.exception("ручной сбор вакансий не удался")
            await message.answer(
                f"{REFRESH_FAILED_TEXT}\n⚠️ {type(error).__name__}: {error}"
            )
            return

        await message.answer(summary_text(stats))

    @router.message(Command("stats"))
    async def stats_command(message: Message) -> None:
        if not allowed(message):
            log.warning("статистика по /stats отклонена: chat=%s", message.from_user.id)
            await message.answer(NO_ACCESS_TEXT)
            return
        try:
            info = await asyncio.to_thread(collect_stats, db_path)
        except Exception:
            log.exception("чтение статистики не удалось")
            await message.answer(STATS_FAILED_TEXT)
            return
        await message.answer(stats_text(info))

    return router
