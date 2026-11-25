from __future__ import annotations

from .normalize import Vacancy
from .ranker import distance_km


def money_text(vacancy: Vacancy) -> str:
    def fmt(number: int) -> str:
        return f"{number:,}".replace(",", " ")

    low, high = vacancy.salary_from, vacancy.salary_to
    if low and high and low != high:
        return f"{fmt(low)} – {fmt(high)} ₽"
    if low:
        return f"от {fmt(low)} ₽"
    if high:
        return f"до {fmt(high)} ₽"
    return "зарплата не указана"


def date_text(vacancy: Vacancy) -> str:
    published = vacancy.published_at or ""
    if len(published) < 10 or published[4] != "-":
        return "дата неизвестна"
    return f"{published[8:10]}.{published[5:7]}"


def place_text(vacancy: Vacancy, home: tuple[float, float] | None = None) -> str:
    if vacancy.is_remote:
        return "удалённо"
    base = vacancy.district or vacancy.city or "—"
    km = distance_km(vacancy, home)
    if km is None:
        return base
    return f"{base} · {km:.1f} км"


def facts_text(vacancy: Vacancy, home: tuple[float, float] | None = None) -> str:
    facts = f"{money_text(vacancy)} · {place_text(vacancy, home)} · {date_text(vacancy)}"
    if vacancy.red_flags:
        facts += " · ⚑ " + ", ".join(vacancy.red_flags)
    return facts
