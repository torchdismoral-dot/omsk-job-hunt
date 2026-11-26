from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .prefs import LOCATIONS, STOP_GROUPS, format_salary, group_selected, location_key
from ..filters import SPHERES

MODE_LABELS = {
    "date": "По дате",
    "salary": "По ЗП",
    "distance": "По близости",
}
SALARY_CHOICES = (30000, 40000, 55000, 80000)
DONATION_STARS = (50, 100, 500)


def main_menu_keyboard(digest_on: bool = True) -> InlineKeyboardMarkup:
    modes = [
        InlineKeyboardButton(text=label, callback_data=f"top:{mode}")
        for mode, label in MODE_LABELS.items()
    ]
    settings = InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")
    digest = InlineKeyboardButton(
        text="🔔 Рассылка: вкл" if digest_on else "🔕 Рассылка: выкл",
        callback_data="digest:toggle",
    )
    donate = InlineKeyboardButton(text="❤️ Поддержать проект", callback_data="donate")
    return InlineKeyboardMarkup(inline_keyboard=[modes, [settings, digest], [donate]])


def donate_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=f"⭐ {stars} Stars", callback_data=f"donate:{stars}")
                for stars in DONATION_STARS
            ]
        ]
    )


def more_keyboard(mode: str, next_offset: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Показать ещё", callback_data=f"more:{mode}:{next_offset}")]
        ]
    )


def onboarding_start_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Поехали", callback_data="ob:go")]
        ]
    )


def location_keyboard(city: str | None, remote: bool) -> InlineKeyboardMarkup:
    current = location_key(city, remote)
    rows = [
        [
            InlineKeyboardButton(
                text=("✅ " if key == current else "") + label,
                callback_data=f"ob:loc:{key}",
            )
        ]
        for key, (label, _, _) in LOCATIONS.items()
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def settings_keyboard(city: str | None, remote: bool) -> InlineKeyboardMarkup:
    rows = list(location_keyboard(city, remote).inline_keyboard)
    rows.append([InlineKeyboardButton(text="🔄 Сбросить всё", callback_data="settings:reset")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def empty_state_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")]
        ]
    )


def spheres_keyboard(selected=()) -> InlineKeyboardMarkup:
    chosen = set(selected)
    rows = [
        [
            InlineKeyboardButton(
                text=("✅ " if key in chosen else "⬜ ") + label,
                callback_data=f"ob:jt:{key}",
            )
        ]
        for key, (label, _) in SPHERES.items()
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text=("✅ " if not chosen else "⬜ ") + "🌐 Без разницы (все)",
                callback_data="ob:jt:any",
            )
        ]
    )
    rows.append([InlineKeyboardButton(text="Готово", callback_data="ob:jt:done")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def stop_words_keyboard(words) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=("✅ " if group_selected(words, key) else "⬜ ") + label,
                callback_data=f"ob:sw:{key}",
            )
        ]
        for key, (label, _) in STOP_GROUPS.items()
    ]
    rows.append([InlineKeyboardButton(text="✏️ Другое (вписать слова)", callback_data="ob:sw:custom")])
    rows.append([InlineKeyboardButton(text="Ничего не исключать", callback_data="ob:sw:none")])
    rows.append([InlineKeyboardButton(text="Готово", callback_data="ob:sw:done")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def salary_keyboard(current: int) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=("✅ " if value == current else "") + format_salary(value),
                callback_data=f"ob:sal:{value}",
            )
        ]
        for value in SALARY_CHOICES
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)
