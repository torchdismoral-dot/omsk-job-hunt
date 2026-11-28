from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .config import Settings
from .db import DB, _now
from .filters import find_flags, is_relevant
from .hh import HHClient, HHError
from .normalize import Vacancy, from_hh, from_superjob, from_trudvsem
from .superjob import SuperJobClient, SuperJobError
from .trudvsem import TrudvsemClient, TrudvsemError

REMOTE_MAX_PAGES = 5
log = logging.getLogger(__name__)


@dataclass
class RawBundle:
    """Сырые ответы площадок и ошибки тех, что не пустили.

    Каждый источник собирается независимо: отказ SuperJob или trudvsem не
    должен обнулять уже полученные данные и остальной сбор.
    """

    superjob: list[dict] = field(default_factory=list)
    trudvsem: list[dict] = field(default_factory=list)
    hh: list[dict] = field(default_factory=list)
    hh_error: str | None = None
    errors: dict[str, str] = field(default_factory=dict)

    def all_errors(self) -> dict[str, str]:
        """Ошибки по источникам, включая hh_error (поле осталось для совместимости)."""
        errors = dict(self.errors)
        if self.hh_error:
            errors.setdefault("hh", self.hh_error)
        return errors


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


def _fetch_superjob(settings: Settings) -> tuple[list[dict], str | None]:
    """Офис по Омску плюс удалёнка. Источник основной, но не единственный."""
    cfg = settings.sources
    try:
        client = SuperJobClient(
            key=settings.superjob_key or "",
            base_url=cfg.superjob_base_url,
            page_size=cfg.page_size,
            delay_ms=cfg.delay_ms,
        )
        office = client.fetch_all(
            max_pages=cfg.max_pages,
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
        return office + remote, None
    except SuperJobError as error:
        log.warning("SuperJob пропущен: %s", error)
        return [], str(error)
    except Exception as error:  # сеть/разметка — пишем и живём дальше
        log.exception("SuperJob: неожиданный сбой сбора")
        return [], f"superjob: {error}"


def _fetch_trudvsem(settings: Settings) -> tuple[list[dict], str | None]:
    """Финляндский источник тоже необязательный: таймаут не роняет прогон."""
    cfg = settings.sources
    try:
        client = TrudvsemClient(
            base_url=cfg.trudvsem_base_url,
            region=cfg.trudvsem_region,
            limit=cfg.trudvsem_limit,
        )
        return client.fetch_all(), None
    except TrudvsemError as error:
        log.warning("trudvsem пропущен: %s", error)
        return [], str(error)
    except Exception as error:
        log.exception("trudvsem: неожиданный сбой сбора")
        return [], f"trudvsem: {error}"


def fetch_raw(settings: Settings) -> RawBundle:
    superjob, superjob_error = _fetch_superjob(settings)
    trudvsem, trudvsem_error = _fetch_trudvsem(settings)
    hh, hh_error = _fetch_hh(settings)
    errors: dict[str, str] = {}
    if superjob_error:
        errors["superjob"] = superjob_error
    if trudvsem_error:
        errors["trudvsem"] = trudvsem_error
    if hh_error:
        errors["hh"] = hh_error
    return RawBundle(
        superjob=superjob,
        trudvsem=trudvsem,
        hh=hh,
        hh_error=hh_error,
        errors=errors,
    )


def refresh(settings: Settings, db: DB) -> dict:
    started_at = _now()
    raw = fetch_raw(settings)
    vacancies = build(raw.superjob, raw.trudvsem, settings, raw.hh)
    fresh = 0
    broken = 0
    for vacancy in vacancies:
        try:
            if db.upsert(vacancy):
                fresh += 1
        except Exception as error:  # одна битая строка не роняет весь прогон
            broken += 1
            log.warning("не сохранилась %s: %s", vacancy.key, error)
    stats = {
        "fetched": len(raw.superjob) + len(raw.trudvsem) + len(raw.hh),
        "relevant": len(vacancies),
        "fresh": fresh,
        "total": db.count(),
        "superjob_fetched": len(raw.superjob),
        "trudvsem_fetched": len(raw.trudvsem),
        "hh_fetched": len(raw.hh),
    }
    errors = raw.all_errors()
    if raw.hh_error:
        stats["hh_error"] = raw.hh_error
    if broken:
        stats["broken"] = broken
        errors["db"] = f"не сохранилось строк: {broken}"
    if errors:
        stats["errors"] = errors
    try:
        db.record_run(stats, started_at)
    except Exception as error:
        log.warning("история прогонов не записана: %s", error)
    return stats
