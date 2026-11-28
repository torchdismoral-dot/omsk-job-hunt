import json
import pathlib
import re

import pytest

from jobhunt.normalize import from_hh, from_superjob, from_trudvsem

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


# --- hh.ru: выдача лежит в JSON-состоянии страницы ---


@pytest.fixture(scope="module")
def hh_vacancies():
    data = json.loads((FIXTURES / "hh_search_omsk.json").read_text(encoding="utf-8"))
    return data["vacancies"]


def test_hh_key_and_source(hh_vacancies):
    obj = hh_vacancies[0]
    v = from_hh(obj)
    assert v.key == f"hh:{obj['vacancyId']}"
    assert v.source == "hh"
    assert v.source_id == str(obj["vacancyId"])


def test_hh_rur_currency_becomes_rub(hh_vacancies):
    obj = next(v for v in hh_vacancies if (v.get("compensation") or {}).get("currencyCode") == "RUR")
    assert from_hh(obj).currency == "RUB"


def test_hh_salary_and_company(hh_vacancies):
    obj = next(
        v for v in hh_vacancies
        if (v.get("compensation") or {}).get("from") and (v.get("compensation") or {}).get("to")
    )
    v = from_hh(obj)
    assert v.salary_from == obj["compensation"]["from"]
    assert v.salary_to == obj["compensation"]["to"]
    assert v.company == obj["company"]["visibleName"]


def test_hh_city_from_area(hh_vacancies):
    assert from_hh(hh_vacancies[0]).city == "Омск"


def test_hh_no_salary_means_not_specified():
    v = from_hh({"vacancyId": 1, "name": "Оператор", "compensation": {"from": 0, "to": None}})
    assert v.salary_from is None
    assert v.salary_to is None


def test_hh_experience_is_translated(hh_vacancies):
    obj = next(v for v in hh_vacancies if v.get("workExperience") == "noExperience")
    assert from_hh(obj).experience == "Без опыта"


def test_hh_unknown_experience_stays_none():
    assert from_hh({"vacancyId": 2, "name": "Оператор", "workExperience": "someCode"}).experience is None
    assert from_hh({"vacancyId": 3, "name": "Оператор"}).experience is None


def test_hh_experience_codes_are_translated():
    assert from_hh({"vacancyId": 30, "name": "О", "workExperience": "between1And3"}).experience == "От 1 года"
    assert from_hh({"vacancyId": 31, "name": "О", "workExperience": "moreThan6"}).experience == "От 6 лет"


def test_hh_remote_from_work_formats():
    v = from_hh({
        "vacancyId": 4,
        "name": "Оператор чата",
        "workFormats": [{"workFormatsElement": ["REMOTE"]}],
    })
    assert v.is_remote is True


def test_hh_office_card_is_not_remote(hh_vacancies):
    obj = next(v for v in hh_vacancies if "REMOTE" not in json.dumps(v.get("workFormats")))
    assert from_hh(obj).is_remote is False


def test_hh_empty_work_formats_block(hh_vacancies):
    obj = next(v for v in hh_vacancies if v.get("workFormats") == [{}])
    assert from_hh(obj).is_remote is False


def test_hh_url_prefers_desktop_link(hh_vacancies):
    obj = next(v for v in hh_vacancies if (v.get("links") or {}).get("desktop"))
    assert from_hh(obj).url == obj["links"]["desktop"]


def test_hh_url_falls_back_to_canonical():
    assert from_hh({"vacancyId": 555, "name": "Оператор"}).url == "https://hh.ru/vacancy/555"


def test_hh_published_is_iso_date(hh_vacancies):
    v = from_hh(hh_vacancies[0])
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", v.published_at)


def test_hh_coordinates_from_marker(hh_vacancies):
    obj = next(v for v in hh_vacancies if (v.get("address") or {}).get("marker"))
    v = from_hh(obj)
    assert v.lat == pytest.approx(obj["address"]["marker"]["@lat"])
    assert v.lng == pytest.approx(obj["address"]["marker"]["@lng"])


def test_hh_without_address_has_no_coordinates():
    v = from_hh({"vacancyId": 7, "name": "Оператор"})
    assert v.lat is None
    assert v.lng is None
    assert v.district is None


def test_hh_district_from_address():
    obj = {"vacancyId": 8, "name": "Оператор", "address": {"displayName": "Омск, Кировский"}}
    assert from_hh(obj).district == "Кировский"


def test_hh_has_no_description(hh_vacancies):
    assert from_hh(hh_vacancies[0]).description is None


def test_hh_keys_do_not_collide_with_other_sources(sj_objects, hh_vacancies):
    assert from_hh(hh_vacancies[0]).key != from_superjob(sj_objects[0]).key
