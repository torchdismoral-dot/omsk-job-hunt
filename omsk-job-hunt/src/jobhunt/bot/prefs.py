from __future__ import annotations

import re

from ..filters import SPHERES

# Ключ -> (подпись кнопки, слова для поиска в вакансии)
STOP_GROUPS: dict[str, tuple[str, tuple[str, ...]]] = {
    "construction": (
        "Стройка/Рабочие",
        (
            "стройк", "стройплощадк", "прораб", "сварщик", "монтажник",
            "бетон", "арматур", "разнорабоч", "маляр", "штукатур", "каменщик",
        ),
    ),
    "sales": (
        "Продажи/Холодные звонки",
        ("продаж", "холодные звонки", "холодный звон", "телемаркетинг"),
    ),
    "callcenter": (
        "Колл-центр",
        ("колл-центр", "call-центр", "колл центр", "контакт-центр"),
    ),
}

# Ключ -> (подпись, город в настройках, разрешать удалёнку)
LOCATIONS: dict[str, tuple[str, str | None, bool]] = {
    "omsk": ("Омск", "Омск", False),
    "remote": ("Удалёнка", None, True),
    "all": ("Всё: Омск и удалёнка", "Омск", True),
}

ALL_GROUP_WORDS = frozenset(word for _, words in STOP_GROUPS.values() for word in words)


def format_salary(value: int) -> str:
    return f"{value:,}".replace(",", " ") + " ₽"


def parse_custom(text: str) -> tuple[str, ...]:
    parts = (part.strip().lower() for part in re.split(r"[,;\n]+", text or ""))
    return tuple(dict.fromkeys(part for part in parts if part))


def group_selected(words, key: str) -> bool:
    group = STOP_GROUPS[key][1]
    return set(group) <= set(words)


def toggle_group(words, key: str) -> tuple[str, ...]:
    group = STOP_GROUPS[key][1]
    words = tuple(words)
    if set(group) <= set(words):
        return tuple(word for word in words if word not in group)
    return words + tuple(word for word in group if word not in words)


def custom_words(words) -> tuple[str, ...]:
    return tuple(word for word in words if word not in ALL_GROUP_WORDS)


def location_key(city: str | None, remote: bool) -> str:
    if remote and city:
        return "all"
    if remote:
        return "remote"
    return "omsk"


def location_label(city: str | None, remote: bool) -> str:
    if remote and city:
        return "Омск и удалёнка"
    if remote:
        return "Удалёнка"
    return city or "Россия"


def stop_words_label(words) -> str:
    words = tuple(words)
    labels = [label for key, (label, _) in STOP_GROUPS.items() if group_selected(words, key)]
    labels += [f"«{word}»" for word in custom_words(words)]
    return ", ".join(labels) or "ничего"


def toggle_sphere(selected, key: str) -> tuple[str, ...]:
    """Пустой набор означает «без разницы»."""
    selected = tuple(selected)
    if key == "any":
        return ()
    if key not in SPHERES:
        return selected
    if key in selected:
        return tuple(item for item in selected if item != key)
    return tuple(item for item in SPHERES if item in selected or item == key)


def spheres_label(job_types) -> str:
    chosen = tuple(job_types)
    labels = [label for key, (label, _) in SPHERES.items() if key in chosen]
    return ", ".join(labels) or "все"


def summary(prefs, has_vacancies: bool = True) -> str:
    """Итог настроек. Хвост зависит от того, нашлось ли что-то под них."""
    tail = (
        "Вот первые 5 вакансий:"
        if has_vacancies
        else "Пока пусто — база наполняется, загляни через пару минут."
    )
    return (
        f"Настройки сохранены! Ищу: {location_label(prefs.city, prefs.remote)}, "
        f"сферы: {spheres_label(prefs.job_types)}, "
        f"ЗП от {format_salary(prefs.min_salary)}, "
        f"исключаю: {stop_words_label(prefs.stop_words)}. "
        + tail
    )
