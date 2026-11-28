import json
import pathlib

from jobhunt.config import Settings
from jobhunt.pipeline import build

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def load_fixtures():
    sj = json.loads((FIXTURES / "superjob_omsk.json").read_text(encoding="utf-8"))["objects"]
    tv_data = json.loads((FIXTURES / "trudvsem_omsk.json").read_text(encoding="utf-8"))
    tv = [item["vacancy"] for item in tv_data["results"]["vacancies"]]
    return sj, tv


def fake_superjob(**kw):
    obj = {
        "id": 1,
        "profession": "Оператор",
        "firm_name": "ООО Тест",
        "town": {"id": 17, "title": "Омск"},
        "address": "Омск",
        "payment_from": 50000,
        "payment_to": 0,
        "currency": "rub",
        "experience": {"id": 0, "title": "Без опыта"},
        "place_of_work": {"id": 1, "title": "На территории работодателя"},
        "link": "https://example.org/1",
        "date_published": 1795634220,
    }
    obj.update(kw)
    return obj


def test_empty_input_gives_empty_result():
    assert build([], [], Settings()) == []


def test_malformed_record_does_not_break_the_run():
    assert build([{}], [{}], Settings()) == []
    result = build([fake_superjob(), {}], [{}, {"no": "id"}], Settings())
    assert len(result) == 1


def test_duplicates_are_dropped():
    sj, tv = load_fixtures()
    result = build(sj + sj, tv + tv, Settings())
    keys = [v.key for v in result]
    assert len(keys) == len(set(keys))


def test_result_stays_within_filters():
    sj, tv = load_fixtures()
    settings = Settings()
    result = build(sj, tv, settings)
    assert result
    for vacancy in result:
        assert vacancy.city == "Омск" or vacancy.is_remote
        assert vacancy.experience in settings.filters.allowed_experience or vacancy.experience is None
        assert vacancy.salary_from is None or vacancy.salary_from >= settings.filters.salary_min


def test_stop_word_vacancy_kept_with_flag():
    result = build([fake_superjob(profession="Менеджер по продажам")], [], Settings())
    assert len(result) == 1
    assert "продаж" in result[0].red_flags


def test_far_vacancy_dropped():
    result = build([fake_superjob(id=2, town={"id": 1, "title": "Москва"}, address="Москва")], [], Settings())
    assert result == []


def test_far_remote_vacancy_kept():
    obj = fake_superjob(id=3, town={"id": 1, "title": "Москва"}, address="Москва")
    obj["place_of_work"] = {"id": 2, "title": "Удалённая работа"}
    result = build([obj], [], Settings())
    assert len(result) == 1
    assert result[0].is_remote


# --- hh.ru как третий источник ---


def fake_hh(**kw):
    obj = {
        "vacancyId": 900,
        "name": "Оператор чата",
        "company": {"visibleName": "ООО Тест"},
        "compensation": {"from": 55000, "to": None, "currencyCode": "RUR"},
        "area": {"name": "Омск"},
        "workExperience": "noExperience",
        "links": {"desktop": "https://hh.ru/vacancy/900"},
        "publicationTime": {"@timestamp": 1795634220},
    }
    obj.update(kw)
    return obj


def test_build_takes_hh_as_third_source():
    result = build([], [], Settings(), [fake_hh()])
    assert [v.key for v in result] == ["hh:900"]


def test_build_skips_malformed_hh_records():
    result = build([], [], Settings(), [{}, {"vacancyId": 1, "name": ""}, fake_hh(vacancyId=2)])
    assert [v.key for v in result] == ["hh:2"]


def test_build_dedupes_same_hh_id():
    assert len(build([], [], Settings(), [fake_hh(), fake_hh()])) == 1


def test_hh_ids_do_not_collide_with_superjob():
    result = build([fake_superjob(id=900)], [], Settings(), [fake_hh()])
    assert {v.key for v in result} == {"superjob:900", "hh:900"}


def test_hh_remote_vacancy_from_other_city_passes():
    obj = fake_hh(
        vacancyId=5,
        area={"name": "Москва"},
        workFormats=[{"workFormatsElement": ["REMOTE"]}],
    )
    assert [v.key for v in build([], [], Settings(), [obj])] == ["hh:5"]


def test_hh_far_office_vacancy_dropped():
    assert build([], [], Settings(), [fake_hh(vacancyId=6, area={"name": "Москва"})]) == []


def test_hh_low_salary_dropped():
    obj = fake_hh(vacancyId=7, compensation={"from": 15000, "currencyCode": "RUR"})
    assert build([], [], Settings(), [obj]) == []


def test_hh_title_drop_word_works():
    assert build([], [], Settings(), [fake_hh(vacancyId=8, name="Дворник")]) == []


def test_hh_stop_word_keeps_vacancy_with_flag():
    result = build([], [], Settings(), [fake_hh(vacancyId=9, name="Менеджер по продажам")])
    assert len(result) == 1
    assert "продаж" in result[0].red_flags


def test_build_from_real_fixture_stays_within_filters():
    data = json.loads((FIXTURES / "hh_search_omsk.json").read_text(encoding="utf-8"))
    settings = Settings()
    result = build([], [], settings, data["vacancies"])
    assert result
    for vacancy in result:
        assert vacancy.city == "Омск" or vacancy.is_remote
        assert vacancy.salary_from is None or vacancy.salary_from >= settings.filters.salary_min


def test_refresh_reports_hh_counts(tmp_path, monkeypatch):
    from jobhunt import pipeline
    from jobhunt.db import DB

    monkeypatch.setattr(
        pipeline, "fetch_raw",
        lambda settings: pipeline.RawBundle(hh=[fake_hh()]),
    )
    db = DB(tmp_path / "r.db")
    try:
        stats = pipeline.refresh(Settings(), db)
    finally:
        db.close()
    assert stats == {
        "fetched": 1, "relevant": 1, "fresh": 1, "total": 1,
        "superjob_fetched": 0, "trudvsem_fetched": 0, "hh_fetched": 1,
    }


def test_refresh_passes_hh_error_through(tmp_path, monkeypatch):
    from jobhunt import pipeline
    from jobhunt.db import DB

    monkeypatch.setattr(
        pipeline, "fetch_raw",
        lambda settings: pipeline.RawBundle(hh_error="hh: HTTP 403 на /search/vacancy"),
    )
    db = DB(tmp_path / "e.db")
    try:
        stats = pipeline.refresh(Settings(), db)
    finally:
        db.close()
    assert stats["hh_fetched"] == 0
    assert "403" in stats["hh_error"]


def test_fetch_raw_survives_blocked_hh(monkeypatch):
    from jobhunt import pipeline
    from jobhunt.hh import HHError

    monkeypatch.setenv("SUPERJOB_KEY", "key")
    monkeypatch.setattr(pipeline.SuperJobClient, "fetch_all", lambda self, **params: [{"id": 1}])
    monkeypatch.setattr(pipeline.TrudvsemClient, "fetch_all", lambda self: [{"id": 2}])

    def blocked(self):
        raise HHError("hh: HTTP 403 на /search/vacancy")

    monkeypatch.setattr(pipeline.HHClient, "fetch_all", blocked)
    bundle = pipeline.fetch_raw(Settings())
    assert len(bundle.superjob) == 2
    assert bundle.hh == []
    assert "403" in bundle.hh_error


def test_fetch_raw_skips_hh_when_disabled(monkeypatch):
    from jobhunt import pipeline

    monkeypatch.setenv("SUPERJOB_KEY", "key")
    monkeypatch.setattr(pipeline.SuperJobClient, "fetch_all", lambda self, **params: [])
    monkeypatch.setattr(pipeline.TrudvsemClient, "fetch_all", lambda self: [])

    def explode(self):
        raise AssertionError("hh выключен — запросов быть не должно")

    monkeypatch.setattr(pipeline.HHClient, "fetch_all", explode)
    settings = Settings()
    settings.sources.hh_enabled = False
    bundle = pipeline.fetch_raw(settings)
    assert bundle.hh == []
    assert bundle.hh_error is None


# --- независимость источников: отказ одного не обнуляет весь прогон ---


def make_clients(monkeypatch, superjob=None, trudvsem=None, hh=None):
    from jobhunt import pipeline

    monkeypatch.setenv("SUPERJOB_KEY", "key")
    if callable(superjob):
        monkeypatch.setattr(pipeline.SuperJobClient, "fetch_all", superjob)
    else:
        monkeypatch.setattr(pipeline.SuperJobClient, "fetch_all", lambda self, **p: list(superjob or []))
    if callable(trudvsem):
        monkeypatch.setattr(pipeline.TrudvsemClient, "fetch_all", trudvsem)
    else:
        monkeypatch.setattr(pipeline.TrudvsemClient, "fetch_all", lambda self: list(trudvsem or []))
    if callable(hh):
        monkeypatch.setattr(pipeline.HHClient, "fetch_all", hh)
    else:
        monkeypatch.setattr(pipeline.HHClient, "fetch_all", lambda self: list(hh or []))
    return pipeline


def test_fetch_raw_survives_superjob_error(monkeypatch):
    from jobhunt.superjob import SuperJobError

    def blocked(self, **params):
        raise SuperJobError("SuperJob: HTTP 403")

    pipeline = make_clients(
        monkeypatch,
        superjob=blocked,
        trudvsem=[{"id": 2}],
        hh=[{"vacancyId": 3}],
    )
    bundle = pipeline.fetch_raw(Settings())
    assert bundle.superjob == []
    assert bundle.trudvsem == [{"id": 2}]
    assert len(bundle.hh) == 2  # офис по Омску и удалёнка по России
    assert "403" in bundle.errors["superjob"]


def test_fetch_raw_survives_trudvsem_error(monkeypatch):
    from jobhunt.trudvsem import TrudvsemError

    def blocked(self):
        raise TrudvsemError("trudvsem: HTTP 500")

    pipeline = make_clients(
        monkeypatch,
        superjob=[{"id": 1}, {"id": 2}],
        trudvsem=blocked,
        hh=[{"vacancyId": 3}],
    )
    bundle = pipeline.fetch_raw(Settings())
    assert len(bundle.superjob) == 4  # офис и удалёнка дают по одному списку
    assert bundle.trudvsem == []
    assert "500" in bundle.errors["trudvsem"]


def test_fetch_raw_never_raises_when_everything_fails(monkeypatch):
    from jobhunt.hh import HHError
    from jobhunt.superjob import SuperJobError
    from jobhunt.trudvsem import TrudvsemError

    def sj(self, **params):
        raise SuperJobError("нет ключа")

    def tv(self):
        raise TrudvsemError("таймаут")

    def hh_(self):
        raise HHError("HTTP 403")

    pipeline = make_clients(monkeypatch, superjob=sj, trudvsem=tv, hh=hh_)
    bundle = pipeline.fetch_raw(Settings())
    assert bundle.superjob == [] and bundle.trudvsem == [] and bundle.hh == []
    assert set(bundle.errors) == {"superjob", "trudvsem", "hh"}


def test_refresh_saves_what_survived(tmp_path, monkeypatch):
    from jobhunt import pipeline
    from jobhunt.db import DB

    monkeypatch.setattr(
        pipeline, "fetch_raw",
        lambda settings: pipeline.RawBundle(
            superjob=[fake_superjob()],
            errors={"trudvsem": "trudvsem: HTTP 500"},
        ),
    )
    db = DB(tmp_path / "p.db")
    try:
        stats = pipeline.refresh(Settings(), db)
    finally:
        db.close()
    assert stats["fresh"] == 1
    assert stats["total"] == 1
    assert stats["errors"]["trudvsem"] == "trudvsem: HTTP 500"


def test_refresh_returns_stats_when_all_sources_failed(tmp_path, monkeypatch):
    from jobhunt import pipeline
    from jobhunt.db import DB

    monkeypatch.setattr(
        pipeline, "fetch_raw",
        lambda settings: pipeline.RawBundle(errors={"superjob": "нет ключа"}),
    )
    db = DB(tmp_path / "a.db")
    try:
        stats = pipeline.refresh(Settings(), db)
    finally:
        db.close()
    assert stats["fetched"] == 0
    assert stats["total"] == 0
    assert stats["errors"] == {"superjob": "нет ключа"}


def test_refresh_counts_every_source_separately(tmp_path, monkeypatch):
    from jobhunt import pipeline
    from jobhunt.db import DB

    monkeypatch.setattr(
        pipeline, "fetch_raw",
        lambda settings: pipeline.RawBundle(
            superjob=[fake_superjob(), fake_superjob(id=2)],
            trudvsem=[{"id": 3}],
            hh=[fake_hh()],
        ),
    )
    db = DB(tmp_path / "c.db")
    try:
        stats = pipeline.refresh(Settings(), db)
    finally:
        db.close()
    assert stats["superjob_fetched"] == 2
    assert stats["trudvsem_fetched"] == 1
    assert stats["hh_fetched"] == 1
    assert stats["fetched"] == 4


def test_refresh_records_run_history(tmp_path, monkeypatch):
    from jobhunt import pipeline
    from jobhunt.db import DB

    monkeypatch.setattr(
        pipeline, "fetch_raw",
        lambda settings: pipeline.RawBundle(hh=[fake_hh()], hh_error="hh: HTTP 403"),
    )
    db = DB(tmp_path / "h.db")
    try:
        pipeline.refresh(Settings(), db)
        run = db.last_run()
    finally:
        db.close()
    assert run["fetched"] == 1
    assert run["fresh"] == 1
    assert "403" in run["error"]
    assert json.loads(run["sources"])["hh"] == 1


def test_refresh_survives_one_broken_row(tmp_path, monkeypatch):
    import sqlite3

    from jobhunt import pipeline
    from jobhunt.db import DB

    monkeypatch.setattr(
        pipeline, "fetch_raw",
        lambda settings: pipeline.RawBundle(
            superjob=[fake_superjob(), fake_superjob(id=2)],
        ),
    )
    db = DB(tmp_path / "b.db")
    real_upsert = db.upsert

    def flaky(vacancy):
        if vacancy.source_id == "2":
            raise sqlite3.IntegrityError("битая строка")
        return real_upsert(vacancy)

    db.upsert = flaky
    try:
        stats = pipeline.refresh(Settings(), db)
    finally:
        db.close()
    assert stats["fresh"] == 1
    assert stats["broken"] == 1
    assert "db" in stats["errors"]
