from __future__ import annotations

from .config import FilterConfig
from .normalize import Vacancy
from .ranker import haversine_km

HOME_CITY = "омск"


def check_geography(vacancy: Vacancy) -> bool:
    return vacancy.is_remote or (vacancy.city or "").strip().lower() == HOME_CITY


def check_experience(vacancy: Vacancy, cfg: FilterConfig) -> bool:
    return vacancy.experience is None or vacancy.experience in cfg.allowed_experience


def check_salary(vacancy: Vacancy, cfg: FilterConfig) -> bool:
    if vacancy.salary_from is not None:
        return vacancy.salary_from >= cfg.salary_min
    if vacancy.salary_to is not None:
        return vacancy.salary_to >= cfg.salary_min
    return cfg.keep_unknown_salary


def _text(vacancy: Vacancy) -> str:
    return " ".join(
        part for part in (vacancy.title, vacancy.company, vacancy.description) if part
    ).lower()


def find_flags(vacancy: Vacancy, stop_words) -> list[str]:
    haystack = _text(vacancy)
    return [word for word in stop_words if word.lower() in haystack]


def is_dropped(vacancy: Vacancy, drop_words, title_drop_words=()) -> bool:
    title = (vacancy.title or "").lower()
    if any(word.lower() in title for word in title_drop_words):
        return True
    haystack = _text(vacancy)
    return any(word.lower() in haystack for word in drop_words)


def check_reach(vacancy: Vacancy, home, limit_km: float) -> bool:
    """Отбрасывает офисные вакансии, которые физически в другом регионе.

    SuperJob помечает «Омск» у объявлений кадровых агентств, хотя работа
    в Приморье или под Петербургом. Координаты выдают подмену.
    """
    if home is None or vacancy.is_remote or vacancy.lat is None or vacancy.lng is None:
        return True
    return haversine_km(home[0], home[1], vacancy.lat, vacancy.lng) <= limit_km


def is_relevant(vacancy: Vacancy, cfg: FilterConfig, home=None) -> bool:
    if is_dropped(vacancy, cfg.drop_words, cfg.title_drop_words):
        return False
    if not check_geography(vacancy):
        return False
    if not check_reach(vacancy, home, cfg.max_distance_km):
        return False
    if not check_experience(vacancy, cfg):
        return False
    if vacancy.company and vacancy.company in cfg.exclude_companies:
        return False
    return check_salary(vacancy, cfg)
