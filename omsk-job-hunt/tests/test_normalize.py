import json
import pathlib
import re

import pytest

from jobhunt.normalize import from_superjob, from_trudvsem

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def sj_objects():
    return json.loads((FIXTURES / "superjob_omsk.json").read_text(encoding="utf-8"))["objects"]


@pytest.fixture(scope="module")
def tv_vacancies():
    data = json.loads((FIXTURES / "trudvsem_omsk.json").read_text(encoding="utf-8"))
    return [v["vacancy"] for v in data["results"]["vacancies"]]


def test_superjob_key_and_source(sj_objects):
    obj = sj_objects[0]
    v = from_superjob(obj)
    assert v.key == f"superjob:{obj['id']}"
    assert v.source == "superjob"
    assert v.source_id == str(obj["id"])


def test_superjob_lowercase_currency_becomes_rub(sj_objects):
    assert from_superjob(sj_objects[0]).currency == "RUB"


def test_superjob_zero_payment_means_not_specified(sj_objects):
    obj = next(o for o in sj_objects if o.get("payment_from") == 0)
    v = from_superjob(obj)
    assert v.salary_from is None
    assert v.salary_to is None


def test_superjob_payment_preserved(sj_objects):
    obj = next(o for o in sj_objects if o.get("payment_from") and o.get("payment_to"))
    v = from_superjob(obj)
    assert v.salary_from == obj["payment_from"]
    assert v.salary_to == obj["payment_to"]


def test_superjob_experience_title(sj_objects):
    obj = next(o for o in sj_objects if o["experience"]["title"] == "Без опыта")
    assert from_superjob(obj).experience == "Без опыта"


def test_superjob_remote_flag(sj_objects):
    obj = next(o for o in sj_objects if o["place_of_work"]["id"] == 2)
    assert from_superjob(obj).is_remote is True
    other = next(o for o in sj_objects if o["place_of_work"]["id"] == 1)
    assert from_superjob(other).is_remote is False


def test_superjob_published_is_iso_date(sj_objects):
    v = from_superjob(sj_objects[0])
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", v.published_at)


def test_superjob_city_from_town(sj_objects):
    assert from_superjob(sj_objects[0]).city == "Омск"


def test_trudvsem_key_and_source(tv_vacancies):
    vac = tv_vacancies[0]
    v = from_trudvsem(vac)
    assert v.key == f"trudvsem:{vac['id']}"
    assert v.source == "trudvsem"


def test_trudvsem_experience_codes(tv_vacancies):
    by_code = {}
    for vac in tv_vacancies:
        code = (vac.get("requirement") or {}).get("experience")
        by_code.setdefault(code, vac)
    if 0 in by_code:
        assert from_trudvsem(by_code[0]).experience == "Без опыта"
    if 1 in by_code:
        assert from_trudvsem(by_code[1]).experience == "От 1 года"
    if 6 in by_code:
        assert from_trudvsem(by_code[6]).experience == "От 6 лет"


def test_trudvsem_city_from_address(tv_vacancies):
    assert from_trudvsem(tv_vacancies[0]).city == "Омск"


def test_trudvsem_salary_numbers(tv_vacancies):
    vac = tv_vacancies[0]
    v = from_trudvsem(vac)
    assert v.salary_from == vac["salary_min"]
    assert v.currency == "RUB"


def test_trudvsem_published_is_iso_date(tv_vacancies):
    v = from_trudvsem(tv_vacancies[0])
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", v.published_at)


def test_keys_do_not_collide(sj_objects, tv_vacancies):
    sj_key = from_superjob(sj_objects[0]).key
    tv_key = from_trudvsem(tv_vacancies[0]).key
    assert sj_key != tv_key


def test_superjob_coordinates(sj_objects):
    obj = next(o for o in sj_objects if o.get("latitude") and float(o["latitude"]) != 0)
    v = from_superjob(obj)
    assert v.lat == float(obj["latitude"])
    assert v.lng == float(obj["longitude"])


def test_superjob_missing_coordinates(sj_objects):
    obj = next(o for o in sj_objects if not o.get("latitude") or float(o["latitude"]) == 0)
    assert from_superjob(obj).lat is None


def test_trudvsem_coordinates(tv_vacancies):
    v = from_trudvsem(tv_vacancies[0])
    assert v.lat == pytest.approx(54.988489)
    assert v.lng == pytest.approx(73.376872)
