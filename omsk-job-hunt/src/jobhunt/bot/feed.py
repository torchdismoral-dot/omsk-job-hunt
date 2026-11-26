from __future__ import annotations

from aiogram.types import Message

from ..config import Settings
from ..db import DB, UserSettings
from ..filters import matches_user
from ..ranker import rank
from .keyboards import MODE_LABELS, empty_state_keyboard, more_keyboard
from .messages import EMPTY_FEED_TEXT, render_pages

PAGE = 10
PER_MESSAGE = 8


def load(db: DB, settings: Settings, prefs: UserSettings | None, mode: str):
    vacancies = db.all()
    if prefs is not None:
        vacancies = [vacancy for vacancy in vacancies if matches_user(vacancy, prefs)]
    return rank(vacancies, mode, settings.home)


async def send_slice(
    message: Message,
    settings: Settings,
    db_path: str,
    mode: str,
    offset: int,
    prefs: UserSettings | None = None,
    limit: int = PAGE,
) -> None:
    db = DB(db_path)
    try:
        vacancies = load(db, settings, prefs, mode)
    finally:
        db.close()
    if not vacancies:
        await message.answer(EMPTY_FEED_TEXT, reply_markup=empty_state_keyboard())
        return
    window = vacancies[offset : offset + limit]
    for page in render_pages(
        window,
        start_index=offset + 1,
        home=settings.home,
        per_message=min(limit, PER_MESSAGE),
    ):
        await message.answer(page)
    if limit == PAGE and offset + PAGE < len(vacancies):
        await message.answer(
            f"{MODE_LABELS.get(mode, mode)}: показано {offset + len(window)} из {len(vacancies)}",
            reply_markup=more_keyboard(mode, offset + PAGE),
        )
