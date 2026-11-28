import html
import json
import pathlib
import urllib.error
import urllib.request

import pytest

from jobhunt.hh import HHClient, HHError, extract_state, last_page, parse_vacancies

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def page(state: dict) -> str:
    """Оборачивает состояние в тот же template, что отдаёт hh.ru."""
    body = html.escape(json.dumps({"vacancySearchResult": state}, ensure_ascii=False), quote=True)
    return f'<template style="display:none" id="HH-Lux-InitialState">{body}</template>'


def make_state(ids, last=0):
    return {
        "vacancies": [{"vacancyId": i, "name": f"Вакансия {i}"} for i in ids],
        "paging": {"lastPage": {"page": last}},
    }


@pytest.fixture(scope="module")
def hh_state():
    return json.loads((FIXTURES / "hh_search_omsk.json").read_text(encoding="utf-8"))


def test_extract_state_reads_template(hh_state):
    assert extract_state(page(hh_state))["totalResults"] == hh_state["totalResults"]


def test_extract_state_on_stub_page_raises():
    with pytest.raises(HHError):
        extract_state("<html><body>Доступ ограничен</body></html>")


def test_extract_state_broken_json_raises():
    with pytest.raises(HHError):
        extract_state('<template id="HH-Lux-InitialState">{не json</template>')


def test_extract_state_without_search_results_raises():
    with pytest.raises(HHError):
        extract_state('<template id="HH-Lux-InitialState">{"other": 1}</template>')


def test_parse_vacancies_skips_ads_and_broken_cards(hh_state):
    cards = list(hh_state["vacancies"])
    cards.insert(0, {"vacancyId": 1, "name": "Рекламная вакансия", "@isAdv": True})
    cards.insert(1, {"vacancyId": 2, "name": "  "})
    cards.insert(2, "не словарь")
    parsed = parse_vacancies({"vacancies": cards})
    ids = {card["vacancyId"] for card in parsed}
    assert 1 not in ids
    assert 2 not in ids
    assert len(parsed) == len(hh_state["vacancies"])


def test_last_page_reads_paging(hh_state):
    assert last_page(hh_state) == int(hh_state["paging"]["lastPage"]["page"])
    assert last_page({}) == 0
    assert last_page({"paging": {"lastPage": {"page": "не число"}}}) == 0


def test_params_office_vs_remote():
    office = HHClient(area=68)._params(2)
    assert office["area"] == 68
    assert office["experience"] == "noExperience"
    assert office["order_by"] == "publication_time"
    assert office["page"] == 2
    assert "work_format" not in office

    remote = HHClient(area=113, remote=True)._params(0)
    assert remote["area"] == 113
    assert remote["work_format"] == "REMOTE"




def test_fetch_all_walks_pages_until_last_page(monkeypatch):
    client = HHClient(max_pages=10, delay_ms=0)
    pages = {0: make_state([1, 2], last=1), 1: make_state([3], last=1)}
    seen = []
    monkeypatch.setattr(
        client, "_get", lambda params: seen.append(params["page"]) or page(pages[params["page"]])
    )
    assert [card["vacancyId"] for card in client.fetch_all()] == [1, 2, 3]
    assert seen == [0, 1]


def test_fetch_all_stops_on_max_pages(monkeypatch):
    client = HHClient(max_pages=3, delay_ms=0)
    monkeypatch.setattr(
        client, "_get", lambda params: page(make_state([params["page"] + 10], last=99))
    )
    assert [card["vacancyId"] for card in client.fetch_all()] == [10, 11, 12]


def test_vacancy_without_id_is_not_a_card():
    # id=0 у hh не бывает, но такая запись не должна попадать в базу
    assert parse_vacancies({"vacancies": [{"vacancyId": 0, "name": "Без id"}]}) == []


def test_fetch_all_stops_on_empty_page(monkeypatch):
    client = HHClient(max_pages=5, delay_ms=0)
    calls = []

    def fake_get(params):
        calls.append(params["page"])
        return page({"vacancies": [], "paging": {"lastPage": {"page": 5}}})

    monkeypatch.setattr(client, "_get", fake_get)
    assert client.fetch_all() == []
    assert calls == [0]


def test_fetch_all_dedupes_repeated_ids(monkeypatch):
    client = HHClient(max_pages=5, delay_ms=0)
    pages = {0: make_state([1, 2], last=1), 1: make_state([2, 3], last=1)}
    monkeypatch.setattr(client, "_get", lambda params: page(pages[params["page"]]))
    assert [card["vacancyId"] for card in client.fetch_all()] == [1, 2, 3]


def test_fetch_all_zero_pages_makes_no_requests(monkeypatch):
    client = HHClient(max_pages=0, delay_ms=0)
    monkeypatch.setattr(client, "_get", lambda params: pytest.fail("запрос не нужен"))
    assert client.fetch_all() == []


def test_http_error_becomes_hh_error():
    error = urllib.error.HTTPError("https://hh.ru/search/vacancy", 403, "Forbidden", None, None)

    class Blocked:
        def open(self, request, timeout=None):
            raise error

    client = HHClient()
    client._opener = Blocked()
    with pytest.raises(HHError, match="403"):
        client._get({"page": 0})


def test_network_error_becomes_hh_error():
    class Down:
        def open(self, request, timeout=None):
            raise urllib.error.URLError("connection refused")

    client = HHClient()
    client._opener = Down()
    with pytest.raises(HHError, match="нет связи"):
        client._get({"page": 0})


def test_get_sends_browser_request():
    recorded = {}

    class Response:
        def read(self):
            return b"ok"

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class Recorder:
        def open(self, request, timeout=None):
            recorded["url"] = request.full_url
            recorded["ua"] = request.get_header("User-agent")
            return Response()

    client = HHClient()
    client._opener = Recorder()
    assert client._get({"page": 0, "text": ""}) == "ok"
    assert "/search/vacancy?" in recorded["url"]
    assert recorded["ua"].startswith("Mozilla/")


def test_proxy_only_with_setting():
    plain = HHClient()
    with_proxy = HHClient(proxy="http://user:pass@host:8080")
    assert not any(isinstance(h, urllib.request.ProxyHandler) for h in plain._opener.handlers)
    assert any(isinstance(h, urllib.request.ProxyHandler) for h in with_proxy._opener.handlers)

def test_params_without_experience_filter():
    assert "experience" not in HHClient(experience="")._params(0)
