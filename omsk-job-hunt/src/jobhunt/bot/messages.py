from __future__ import annotations

import html

from ..normalize import Vacancy
from ..render import facts_text

MAX_MESSAGE = 4000
PER_MESSAGE = 8

EMPTY_FEED_TEXT = (
    "По твоим фильтрам пока пусто 😔\n"
    "Попробуй:\n"
    "• Снизить минимальную ЗП (например, до 30 000 ₽)\n"
    "• Добавить сферы в ⚙️ Настройках\n"
    "• Заглянуть позже (база обновляется каждые 48 часов)"
)

EMPTY_DB_TEXT = (
    "База пока пустая — вакансии ещё не успели собраться 😴\n"
    "Дело не в твоих фильтрах: сбор стартует сам сразу после запуска бота "
    "и потом каждые 48 часов.\n"
    "Загляни сюда через пару минут."
)

DONATE_TEXT = (
    "Привет! Я делаю этого бота один, в свободное время. "
    "Если он экономит твоё время, ты можешь поддержать проект. "
    "Любая сумма — мотивация пилить новые фичи! 🚀"
)

DONATION_THANKS = (
    "Огромное спасибо за поддержку! 🫶 Ты лучший. "
    "Твой вклад помогает боту становиться лучше."
)

NO_ACCESS_TEXT = "Нет доступа."
REFRESH_START_TEXT = "Начинаю сбор вакансий..."
REFRESH_FAILED_TEXT = "Сбор не удался, подробности в логах."
STATS_FAILED_TEXT = "Не удалось прочитать статистику, подробности в логах."


def vacancy_html(index: int, vacancy: Vacancy, home: tuple[float, float] | None = None) -> str:
    head = f"<b>{index}. {html.escape(vacancy.title)}</b>"
    if vacancy.company:
        head += f" — {html.escape(vacancy.company)}"
    return f"{head}\n{html.escape(facts_text(vacancy, home))}\n{vacancy.url}"


def render_pages(
    vacancies: list[Vacancy],
    start_index: int = 1,
    home: tuple[float, float] | None = None,
    per_message: int = PER_MESSAGE,
) -> list[str]:
    pages: list[str] = []
    for offset in range(0, len(vacancies), per_message):
        chunk = vacancies[offset : offset + per_message]
        blocks = [
            vacancy_html(start_index + offset + position, vacancy, home)
            for position, vacancy in enumerate(chunk)
        ]
        pages.append("\n\n".join(blocks))
    return pages
