import pytest

from jobhunt.superjob import SuperJobClient, SuperJobError


def test_key_is_required():
    with pytest.raises(SuperJobError):
        SuperJobClient("")


def test_page_size_is_capped_at_40():
    assert SuperJobClient("key", page_size=100).page_size == 40


def test_fetch_all_walks_pages_until_more_false(monkeypatch):
    pages = {
        0: {"objects": [{"id": 1}], "more": True},
        1: {"objects": [{"id": 2}], "more": False},
    }
    seen = []
    client = SuperJobClient("key", delay_ms=0)
    monkeypatch.setattr(
        client, "_get", lambda path, params: seen.append(params["page"]) or pages[params["page"]]
    )
    result = client.fetch_all(max_pages=10, town=17)
    assert [o["id"] for o in result] == [1, 2]
    assert seen == [0, 1]


def test_fetch_all_stops_on_empty_page(monkeypatch):
    client = SuperJobClient("key", delay_ms=0)
    monkeypatch.setattr(client, "_get", lambda path, params: {"objects": [], "more": True})
    assert client.fetch_all(max_pages=5) == []


def test_fetch_all_respects_max_pages(monkeypatch):
    client = SuperJobClient("key", delay_ms=0)
    monkeypatch.setattr(
        client, "_get", lambda path, params: {"objects": [{"id": params["page"]}], "more": True}
    )
    assert len(client.fetch_all(max_pages=3)) == 3
