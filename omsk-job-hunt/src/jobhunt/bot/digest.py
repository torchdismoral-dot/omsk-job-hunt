from __future__ import annotations

import logging

from ..config import Settings
from ..db import DB
from ..ranker import rank
from .messages import render_pages

log = logging.getLogger(__name__)

DIGEST_LIMIT = 5


def pick(db: DB, settings: Settings, chat_id: int, limit: int = DIGEST_LIMIT):
    """Свежие вакансии, которых этому чату ещё не присылали."""
    return rank(db.unsent(chat_id), "date", settings.home)[:limit]


async def send_digest(bot, db: DB, settings: Settings, chat_id: int,
                      limit: int = DIGEST_LIMIT) -> int:
    chosen = pick(db, settings, chat_id, limit)
    if not chosen:
        return 0
    for page in render_pages(chosen, home=settings.home):
        await bot.send_message(chat_id, page)
    db.mark_sent([vacancy.key for vacancy in chosen], chat_id, "digest")
    return len(chosen)


async def send_digests(bot, db: DB, settings: Settings) -> int:
    total = 0
    for chat_id in db.subscribers():
        try:
            total += await send_digest(bot, db, settings, chat_id)
        except Exception:
            log.exception("дайджест для чата %s не ушёл", chat_id)
    return total
