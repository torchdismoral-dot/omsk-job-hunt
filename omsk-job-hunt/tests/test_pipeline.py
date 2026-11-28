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
        "fetched": 1, "relevant": 1, "fresh": 1, "total": 1, "hh_fetched": 1,
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
