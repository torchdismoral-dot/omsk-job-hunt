from __future__ import annotations

from .config import FilterConfig
from .normalize import Vacancy

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


def is_dropped(vacancy: Vacancy, drop_words) -> bool:
    haystack = _text(vacancy)
    return any(word.lower() in haystack for word in drop_words)


def is_relevant(vacancy: Vacancy, cfg: FilterConfig) -> bool:
    if is_dropped(vacancy, cfg.drop_words):
        return False
    if not check_geography(vacancy):
        return False
    if not check_experience(vacancy, cfg):
        return False
    if vacancy.company and vacancy.company in cfg.exclude_companies:
        return False
    return check_salary(vacancy, cfg)
