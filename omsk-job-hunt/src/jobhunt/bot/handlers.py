from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from ..config import Settings
from ..db import DB
from ..ranker import rank
from .digest import send_digest
from .keyboards import MODE_LABELS, modes_keyboard, more_keyboard
from .messages import render_pages

PAGE = 10
log = logging.getLogger(__name__)


def build_router(settings: Settings, db_path: str) -> Router:
    router = Router()

    def load(mode: str):
        db = DB(db_path)
        try:
            return rank(db.all(), mode, settings.home)
        finally:
            db.close()

    async def send_slice(message: Message, mode: str, offset: int) -> None:
        vacancies = load(mode)
        if not vacancies:
            await message.answer("База пустая. Запусти refresh на компьютере.")
            return
        window = vacancies[offset : offset + PAGE]
        for page in render_pages(window, start_index=offset + 1, home=settings.home):
            await message.answer(page)
        if offset + PAGE < len(vacancies):
            await message.answer(
                f"{MODE_LABELS.get(mode, mode)}: показано {offset + len(window)} из {len(vacancies)}",
                reply_markup=more_keyboard(mode, offset + PAGE),
            )

    @router.message(CommandStart())
    async def start(message: Message) -> None:
        await message.answer(
            "Привет. Собираю вакансии без опыта по Омску и удалёнке. "
            "Выбери, как отсортировать.\n\n"
            "/subscribe — присылать новые раз в 2 дня.",
            reply_markup=modes_keyboard(),
        )

    @router.message(Command("subscribe"))
    async def subscribe(message: Message) -> None:
        db = DB(db_path)
        try:
            db.subscribe(message.chat.id)
            sent = await send_digest(message.bot, db, settings, message.chat.id)
        finally:
            db.close()
        if sent:
            await message.answer(
                f"Подписка включена. Это первые {sent} — дальше раз в "
                f"{settings.digest_hours} ч буду присылать только новое. "
                "/unsubscribe — отключить."
            )
        else:
            await message.answer(
                f"Подписка включена. Нового пока нет — пришлю раз в "
                f"{settings.digest_hours} ч, если появится."
            )

    @router.message(Command("unsubscribe"))
    async def unsubscribe(message: Message) -> None:
        db = DB(db_path)
        try:
            db.unsubscribe(message.chat.id)
        finally:
            db.close()
        await message.answer("Подписка выключена. /subscribe — вернуть.")

    @router.message(Command("top"))
    async def top(message: Message) -> None:
        await message.answer("Как отсортировать?", reply_markup=modes_keyboard())

    @router.callback_query(F.data.startswith("top:"))
    async def show_top(callback: CallbackQuery) -> None:
        mode = callback.data.split(":", 1)[1]
        if mode not in MODE_LABELS:
            await callback.answer("Неизвестный режим")
            return
        await callback.answer()
        await send_slice(callback.message, mode, 0)

    @router.callback_query(F.data.startswith("more:"))
    async def show_more(callback: CallbackQuery) -> None:
        try:
            _, mode, offset = callback.data.split(":")
            offset = int(offset)
        except ValueError:
            await callback.answer("Сломалась кнопка")
            return
        await callback.answer()
        await send_slice(callback.message, mode, offset)

    return router
