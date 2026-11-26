from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from ..config import Settings
from ..db import DB
from .digest import send_digest
from .donations import build_donate_router
from .feed import send_slice
from .keyboards import MODE_LABELS, main_menu_keyboard
from .onboarding import build_onboarding_router

log = logging.getLogger(__name__)


def build_router(settings: Settings, db_path: str) -> Router:
    router = Router()
    router.include_router(build_onboarding_router(settings, db_path))
    router.include_router(build_donate_router(settings, db_path))

    def prefs_for(user_id: int):
        db = DB(db_path)
        try:
            return db.get_user_settings(user_id)
        finally:
            db.close()

    @router.message(Command("subscribe"))
    async def subscribe(message: Message) -> None:
        db = DB(db_path)
        try:
            prefs = db.get_user_settings(message.from_user.id)
            if prefs is None:
                await message.answer("Сначала настроим выдачу: нажми /start.")
                return
            db.set_digest_enabled(prefs.user_id, True)
            sent = await send_digest(message.bot, db, settings, prefs.user_id)
        finally:
            db.close()
        if sent:
            await message.answer(
                f"Рассылка включена. Это первые {sent} — дальше раз в "
                f"{settings.digest_hours} ч буду присылать только новое. "
                "/stop_digest — отключить."
            )
        else:
            await message.answer(
                f"Рассылка включена. Нового пока нет — пришлю раз в "
                f"{settings.digest_hours} ч, если появится."
            )

    @router.message(Command("unsubscribe"))
    async def unsubscribe(message: Message) -> None:
        db = DB(db_path)
        try:
            if db.get_user_settings(message.from_user.id) is None:
                await message.answer("Сначала настроим выдачу: нажми /start.")
                return
            db.set_digest_enabled(message.from_user.id, False)
        finally:
            db.close()
        await message.answer("Рассылка выключена. /stop_digest — включить снова.")

    @router.message(Command("stop_digest"))
    async def stop_digest(message: Message) -> None:
        db = DB(db_path)
        try:
            prefs = db.get_user_settings(message.from_user.id)
            if prefs is None:
                await message.answer("Сначала настроим выдачу: нажми /start.")
                return
            enabled = not prefs.digest_enabled
            db.set_digest_enabled(prefs.user_id, enabled)
        finally:
            db.close()
        if enabled:
            await message.answer("Рассылка включена. /stop_digest — выключить.")
        else:
            await message.answer("Рассылка выключена. /stop_digest — включить снова.")

    @router.callback_query(F.data == "digest:toggle")
    async def toggle_digest(callback: CallbackQuery) -> None:
        db = DB(db_path)
        try:
            prefs = db.get_user_settings(callback.from_user.id)
            if prefs is None:
                await callback.answer("Сначала настроим выдачу: /start", show_alert=True)
                return
            enabled = not prefs.digest_enabled
            db.set_digest_enabled(prefs.user_id, enabled)
        finally:
            db.close()
        await callback.answer("Рассылка включена" if enabled else "Рассылка выключена")
        await callback.message.edit_reply_markup(reply_markup=main_menu_keyboard(enabled))

    @router.message(Command("top"))
    async def top(message: Message) -> None:
        prefs = prefs_for(message.from_user.id)
        if prefs is None:
            await message.answer("Сначала настроим выдачу: нажми /start.")
            return
        await message.answer(
            "Как отсортировать?", reply_markup=main_menu_keyboard(prefs.digest_enabled)
        )

    @router.callback_query(F.data.startswith("top:"))
    async def show_top(callback: CallbackQuery) -> None:
        mode = callback.data.split(":", 1)[1]
        if mode not in MODE_LABELS:
            await callback.answer("Неизвестный режим")
            return
        prefs = prefs_for(callback.from_user.id)
        if prefs is None:
            await callback.answer("Нажми /start", show_alert=True)
            return
        await callback.answer()
        await send_slice(callback.message, settings, db_path, mode, 0, prefs)

    @router.callback_query(F.data.startswith("more:"))
    async def show_more(callback: CallbackQuery) -> None:
        try:
            _, mode, offset = callback.data.split(":")
            offset = int(offset)
        except ValueError:
            await callback.answer("Сломалась кнопка")
            return
        prefs = prefs_for(callback.from_user.id)
        await callback.answer()
        await send_slice(callback.message, settings, db_path, mode, offset, prefs)

    return router
