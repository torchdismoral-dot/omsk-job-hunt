from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

MODE_LABELS = {
    "date": "По дате",
    "salary": "По ЗП",
    "distance": "По близости",
}


def modes_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(text=label, callback_data=f"top:{mode}")
        for mode, label in MODE_LABELS.items()
    ]
    return InlineKeyboardMarkup(inline_keyboard=[buttons])


def more_keyboard(mode: str, next_offset: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Показать ещё", callback_data=f"more:{mode}:{next_offset}")]
        ]
    )
