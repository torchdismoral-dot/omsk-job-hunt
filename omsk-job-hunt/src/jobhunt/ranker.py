from __future__ import annotations

import math
from collections.abc import Iterable

from .normalize import Vacancy

EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def distance_km(vacancy: Vacancy, home: tuple[float, float] | None) -> float | None:
    if home is None or vacancy.lat is None or vacancy.lng is None:
        return None
    return haversine_km(home[0], home[1], vacancy.lat, vacancy.lng)


def by_date(vacancies: Iterable[Vacancy]) -> list[Vacancy]:
    return sorted(
        vacancies,
        key=lambda v: (v.published_at or "", v.published_at is not None),
        reverse=True,
    )


def by_salary(vacancies: Iterable[Vacancy]) -> list[Vacancy]:
    return sorted(
        vacancies,
        key=lambda v: (v.salary_from is None, -(v.salary_from or 0)),
    )


def distance_rank(vacancy: Vacancy) -> int:
    if vacancy.is_remote:
        return 3
    if vacancy.district == "Кировский":
        return 0
    if vacancy.district == "Центральный":
        return 1
    return 2


def by_distance(vacancies: Iterable[Vacancy], home: tuple[float, float] | None = None) -> list[Vacancy]:
    """Сначала близкие по координатам, затем известный район, затем остальной Омск, потом удалёнка."""

    def key(vacancy: Vacancy):
        if vacancy.is_remote:
            return (3, 0.0)
        meters = distance_km(vacancy, home)
        if meters is not None:
            return (0, meters)
        rank = distance_rank(vacancy)
        return (1 if rank < 2 else 2, float(rank))

    return sorted(by_date(vacancies), key=key)


RANKERS = {"date": by_date, "salary": by_salary}


def dedupe(vacancies: Iterable[Vacancy]) -> list[Vacancy]:
    """Склеивает повторы одной вакансии: та же должность, компания и зарплата.

    Работодатели публикуют одну вакансию десятками копий, у каждой свой id.
    """
    seen = set()
    unique = []
    for vacancy in vacancies:
        key = (
            (vacancy.title or "").strip().lower(),
            (vacancy.company or "").strip().lower(),
            vacancy.salary_from,
            vacancy.salary_to,
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(vacancy)
    return unique


def rank(vacancies: Iterable[Vacancy], mode: str, home: tuple[float, float] | None = None) -> list[Vacancy]:
    if mode == "distance":
        return dedupe(by_distance(vacancies, home))
    try:
        ranker = RANKERS[mode]
    except KeyError:
        raise ValueError(f"unknown ranking mode: {mode}") from None
    return dedupe(ranker(vacancies))
