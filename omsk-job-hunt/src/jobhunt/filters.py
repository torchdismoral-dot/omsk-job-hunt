from __future__ import annotations

import re

from .config import FilterConfig
from .db import UserSettings
from .normalize import Vacancy
from .ranker import haversine_km

HOME_CITY = "омск"

# Ключ -> (подпись кнопки, шаблон по названию вакансии)
SPHERES: dict[str, tuple[str, re.Pattern[str]]] = {
    "banking": (
        "💼 Банки и финансы",
        re.compile(
            r"банк|кредит|финанс|бухгалтер|кассир|операционист|бэк-офис"
            r"|экономист|страхов|физических лиц"
        ),
    ),
    "it": (
        "💻 IT и интернет",
        re.compile(
            r"\bit\b|айти|тестировщик|qa|программист|разработчик|хелпдеск"
            r"|helpdesk|системный админ|аналитик данных|support"
        ),
    ),
    "support": (
        "📞 Клиентский сервис",
        re.compile(
            r"поддержк|клиентск|оператор.*(?:чат|связи)|сервис|vip"
            r"|обслуживан\w*\s+(?:физических лиц|клиентов)"
        ),
    ),
    "admin": (
        "🗂 Административный персонал",
        re.compile(
            r"ассистент|секретар|делопроизводител|офис-менеджер|документооборот"
        ),
    ),
    "sales": (
        "🛒 Продажи",
        re.compile(r"продаж|торгов|менеджер по работе с клиентами|магазин|администратор"),
    ),
    "logistics": (
        "🚚 Логистика",
        re.compile(
            r"курьер|логист|кладовщик|комплектовщик|водитель|склад"
            r"|экспедитор|доставк"
        ),
    ),
    "blue_collar": (
        "🛠 Рабочие",
        re.compile(
            r"мастер|сварщик|грузчик|монтажник|электрик|сантехник|бетон"
            r"|отделоч|разнорабоч|прораб|маляр|штукатур|арматур|слесар"
            r"|машинист|рабочий"
        ),
    ),
}


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


def check_user_location(vacancy: Vacancy, prefs: UserSettings) -> bool:
    """Локация из настроек: city=None — только удалёнка, иначе офис в городе
    плюс удалёнка, если prefs.remote."""
    if prefs.remote and vacancy.is_remote:
        return True
    if prefs.city and not vacancy.is_remote:
        return (vacancy.city or "").strip().lower() == prefs.city.strip().lower()
    return False


def check_user_salary(vacancy: Vacancy, min_salary: int) -> bool:
    if vacancy.salary_from is not None:
        return vacancy.salary_from >= min_salary
    if vacancy.salary_to is not None:
        return vacancy.salary_to >= min_salary
    return True


def check_job_types(vacancy: Vacancy, job_types) -> bool:
    """Сфера: строго по названию вакансии, не по описанию.

    Пустой набор означает «без разницы».
    """
    chosen = tuple(job_types or ())
    if not chosen:
        return True
    title = (vacancy.title or "").lower()
    return any(
        pattern.search(title)
        for key, (_, pattern) in SPHERES.items()
        if key in chosen
    )


def matches_user(vacancy: Vacancy, prefs: UserSettings) -> bool:
    """Персональные фильтры поверх общих: локация, сфера, стоп-слова, порог ЗП."""
    if not check_user_location(vacancy, prefs):
        return False
    if not check_job_types(vacancy, prefs.job_types):
        return False
    if find_flags(vacancy, prefs.stop_words):
        return False
    return check_user_salary(vacancy, prefs.min_salary)
