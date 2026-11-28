from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .config import Settings
from .db import DB
from .filters import find_flags, is_relevant
from .hh import HHClient, HHError
from .normalize import Vacancy, from_hh, from_superjob, from_trudvsem
from .superjob import SuperJobClient
from .trudvsem import TrudvsemClient

REMOTE_MAX_PAGES = 5
log = logging.getLogger(__name__)


@dataclass
class RawBundle:
    """Сырые ответы всех площадок плюс ошибка hh, если он не пустил."""

    superjob: list[dict] = field(default_factory=list)
    trudvsem: list[dict] = field(default_factory=list)
    hh: list[dict] = field(default_factory=list)
    hh_error: str | None = None


def build(raw_superjob, raw_trudvsem, settings: Settings, raw_hh=()) -> list[Vacancy]:
    """Нормализует и фильтрует сырые ответы трёх площадок."""
    seen: set[str] = set()
    result: list[Vacancy] = []

    def add(normalizer, raw: dict) -> None:
        try:
            vacancy = normalizer(raw)
        except (KeyError, TypeError, ValueError, AttributeError):
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
    for obj in raw_hh:
        add(from_hh, obj)
    return result


def _hh_clients(settings: Settings) -> list[HHClient]:
    """Два прогона: офис по Омску и удалёнка по всей России."""
    cfg = settings.sources
    common = {
        "base_url": cfg.hh_base_url,
        "experience": cfg.hh_experience,
        "search_period_days": cfg.hh_search_period_days,
        "delay_ms": cfg.hh_delay_ms,
        "proxy": settings.hh_proxy,
    }
    clients = [HHClient(area=cfg.hh_area_omsk, max_pages=cfg.hh_max_pages_omsk, **common)]
    if cfg.hh_area_remote:
        clients.append(
            HHClient(
                area=cfg.hh_area_remote,
                remote=True,
                max_pages=cfg.hh_max_pages_remote,
                **common,
            )
        )
    return clients


def _fetch_hh(settings: Settings) -> tuple[list[dict], str | None]:
    """hh — источник необязательный: отказ не должен ронять сбор SuperJob."""
    if not settings.sources.hh_enabled:
        return [], None
    collected: list[dict] = []
    errors: list[str] = []
    for client in _hh_clients(settings):
        try:
            collected.extend(client.fetch_all())
        except HHError as error:
            log.warning("hh пропущен: %s", error)
            errors.append(str(error))
        except Exception as error:  # площадка меняет разметку — пишем и живём дальше
            log.exception("hh: неожиданный сбой сбора")
            errors.append(f"hh: {error}")
    return collected, "; ".join(errors) or None


def fetch_raw(settings: Settings) -> RawBundle:
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
    hh, hh_error = _fetch_hh(settings)
    return RawBundle(superjob=office + remote, trudvsem=trudvsem, hh=hh, hh_error=hh_error)


def refresh(settings: Settings, db: DB) -> dict:
    raw = fetch_raw(settings)
    vacancies = build(raw.superjob, raw.trudvsem, settings, raw.hh)
    fresh = sum(1 for vacancy in vacancies if db.upsert(vacancy))
    stats = {
        "fetched": len(raw.superjob) + len(raw.trudvsem) + len(raw.hh),
        "relevant": len(vacancies),
        "fresh": fresh,
        "total": db.count(),
        "hh_fetched": len(raw.hh),
    }
    if raw.hh_error:
        stats["hh_error"] = raw.hh_error
    return stats
