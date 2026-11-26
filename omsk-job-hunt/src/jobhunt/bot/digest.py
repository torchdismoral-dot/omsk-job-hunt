from __future__ import annotations

import logging

from ..config import Settings
from ..db import DB
from ..filters import matches_user
from ..ranker import rank
from .messages import render_pages

log = logging.getLogger(__name__)

DIGEST_LIMIT = 5


def pick(db: DB, settings: Settings, user_id: int, limit: int = DIGEST_LIMIT):
    """Свежие вакансии, которых этому пользователю ещё не присылали."""
    prefs = db.get_user_settings(user_id)
    pool = db.unsent(user_id)
    if prefs is not None:
        pool = [vacancy for vacancy in pool if matches_user(vacancy, prefs)]
    return rank(pool, "date", settings.home)[:limit]


async def send_digest(bot, db: DB, settings: Settings, user_id: int,
                      limit: int = DIGEST_LIMIT) -> int:
    chosen = pick(db, settings, user_id, limit)
    if not chosen:
        return 0
    for page in render_pages(chosen, home=settings.home):
        await bot.send_message(user_id, page)
    db.mark_sent([vacancy.key for vacancy in chosen], user_id)
    return len(chosen)


async def send_digests(bot, db: DB, settings: Settings) -> int:
    """Рассылка всем, кто прошёл онбординг и не отключил её."""
    total = 0
    for prefs in db.digest_recipients():
        try:
            total += await send_digest(bot, db, settings, prefs.user_id)
        except Exception:
            log.exception("дайджест для пользователя %s не ушёл", prefs.user_id)
    return total
