import asyncio

import pytest
from aiogram.exceptions import TelegramNetworkError

from jobhunt.bot.app import poll_forever
from jobhunt.bot.keyboards import more_keyboard, modes_keyboard
from jobhunt.bot.messages import render_pages, vacancy_html
from jobhunt.normalize import Vacancy


def V(**kw):
    base = dict(
        key="superjob:1",
        source="superjob",
        source_id="1",
        title="Оператор",
        company="ООО Тест",
        salary_from=50000,
        currency="RUB",
        city="Омск",
        url="https://example.org/1",
        published_at="2026-11-25",
    )
    base.update(kw)
    return Vacancy(**base)


def test_title_is_escaped():
    out = vacancy_html(1, V(title="Оператор <b>смены</b>"))
    assert out.startswith("<b>1. ")
    assert "&lt;b&gt;" in out
    assert "<b>смены</b>" not in out


def test_company_and_facts_rendered():
    out = vacancy_html(3, V())
    assert "ООО Тест" in out
    assert "от 50 000 ₽" in out
    assert "25.11" in out
    assert "https://example.org/1" in out


def test_pages_split_by_eight():
    vacancies = [V(key=str(i)) for i in range(20)]
    pages = render_pages(vacancies)
    assert len(pages) == 3
    assert pages[0].startswith("<b>1. ")
    assert "<b>9. " in pages[1]
    assert "<b>17. " in pages[2]


def test_numbering_continues_from_offset():
    pages = render_pages([V(key=str(i)) for i in range(4)], start_index=11)
    assert pages[0].startswith("<b>11. ")


def test_page_fits_telegram_limit():
    vacancies = [V(title="Очень длинное название вакансии " * 5) for _ in range(20)]
    for page in render_pages(vacancies):
        assert len(page) < 4096


def test_modes_keyboard_callbacks():
    keyboard = modes_keyboard()
    data = [button.callback_data for row in keyboard.inline_keyboard for button in row]
    assert data == ["top:date", "top:salary", "top:distance"]


def test_more_keyboard_callback():
    keyboard = more_keyboard("salary", 10)
    assert keyboard.inline_keyboard[0][0].callback_data == "more:salary:10"


def test_poll_forever_survives_network_errors():
    class FlakyDispatcher:
        def __init__(self):
            self.calls = 0

        async def start_polling(self, bot):
            self.calls += 1
            if self.calls < 3:
                raise TelegramNetworkError(None, "Cannot connect to host api.telegram.org:443")

    dispatcher = FlakyDispatcher()
    asyncio.run(poll_forever(object(), dispatcher, delay=0))
    assert dispatcher.calls == 3


def test_poll_forever_does_not_hide_token_errors():
    class BrokenDispatcher:
        async def start_polling(self, bot):
            raise RuntimeError("Unauthorized")

    with pytest.raises(RuntimeError, match="Unauthorized"):
        asyncio.run(poll_forever(object(), BrokenDispatcher(), delay=0))
