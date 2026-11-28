"""Снимает свежую выдачу hh.ru в тестовую фикстуру.

Тесты обязаны работать без сети, поэтому JSON состояния сохраняем в файл.
Запускать вручную, когда hh меняет разметку:

    python scripts/fetch_hh_fixture.py
"""

from __future__ import annotations

import json
import pathlib
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from jobhunt.hh import DEFAULT_UA, extract_state, parse_vacancies  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"
URL = (
    "https://hh.ru/search/vacancy?text=&area=68&experience=noExperience"
    "&search_period=2&order_by=publication_time&page=0"
)
KEEP_VACANCIES = 20


def main() -> int:
    request = urllib.request.Request(
        URL,
        headers={
            "User-Agent": DEFAULT_UA,
            "Accept-Language": "ru-RU,ru;q=0.9",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urllib.request.urlopen(request, timeout=40) as response:
        page = response.read().decode("utf-8", "replace")

    state = extract_state(page)
    vacancies = parse_vacancies(state)[:KEEP_VACANCIES]
    data = {
        "totalResults": state.get("totalResults"),
        "criteria": state.get("criteria"),
        "paging": state.get("paging"),
        "vacancies": vacancies,
    }
    path = FIXTURES / "hh_search_omsk.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"сохранено {path.name}: {len(vacancies)} карточек, всего в выдаче {data['totalResults']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
