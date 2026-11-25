from __future__ import annotations

from .config import Settings
from .db import DB
from .filters import find_flags, is_relevant
from .normalize import Vacancy, from_superjob, from_trudvsem
from .superjob import SuperJobClient
from .trudvsem import TrudvsemClient

REMOTE_MAX_PAGES = 5


def build(raw_superjob, raw_trudvsem, settings: Settings) -> list[Vacancy]:
    """Нормализует и фильтрует сырые ответы двух площадок."""
    seen: set[str] = set()
    result: list[Vacancy] = []

    def add(normalizer, raw: dict) -> None:
        try:
            vacancy = normalizer(raw)
        except (KeyError, TypeError, ValueError):
            return
        if vacancy.key in seen:
            return
        seen.add(vacancy.key)
        vacancy.red_flags = find_flags(vacancy, settings.filters.stop_words)
        if is_relevant(vacancy, settings.filters, settings.home):
            result.append(vacancy)

    for obj in raw_superjob:
        add(from_superjob, obj)
    for vac in raw_trudvsem:
        add(from_trudvsem, vac)
    return result


def fetch_raw(settings: Settings) -> tuple[list[dict], list[dict]]:
    client = SuperJobClient(
        key=settings.superjob_key or "",
        base_url=settings.sources.superjob_base_url,
        page_size=settings.sources.page_size,
        delay_ms=settings.sources.delay_ms,
    )
    office = client.fetch_all(
        max_pages=settings.sources.max_pages,
        town=settings.town_omsk,
        period=2,
        order_field="date",
        order_direction="desc",
    )
    remote = client.fetch_all(
        max_pages=REMOTE_MAX_PAGES,
        place_of_work=2,
        period=2,
        order_field="date",
        order_direction="desc",
    )
    trudvsem = TrudvsemClient(
        base_url=settings.sources.trudvsem_base_url,
        region=settings.sources.trudvsem_region,
        limit=settings.sources.trudvsem_limit,
    ).fetch_all()
    return office + remote, trudvsem


def refresh(settings: Settings, db: DB) -> dict:
    raw_superjob, raw_trudvsem = fetch_raw(settings)
    vacancies = build(raw_superjob, raw_trudvsem, settings)
    fresh = sum(1 for vacancy in vacancies if db.upsert(vacancy))
    return {
        "fetched": len(raw_superjob) + len(raw_trudvsem),
        "relevant": len(vacancies),
        "fresh": fresh,
        "total": db.count(),
    }
