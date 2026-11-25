from __future__ import annotations

import html

from ..normalize import Vacancy
from ..render import facts_text

MAX_MESSAGE = 4000
PER_MESSAGE = 8


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
