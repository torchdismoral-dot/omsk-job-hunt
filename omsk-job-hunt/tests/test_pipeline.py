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
