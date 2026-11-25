import pytest

from jobhunt.config import FilterConfig
from jobhunt.filters import find_flags, is_relevant
from jobhunt.normalize import Vacancy


def V(**kw):
    base = dict(
        key="superjob:1",
        source="superjob",
        source_id="1",
        title="Оператор",
        company="ООО",
        salary_from=None,
        salary_to=None,
        currency="RUB",
        city="Омск",
        district=None,
        is_remote=False,
        experience="Не имеет значения",
        url="https://example.org/1",
        published_at="2026-11-25",
    )
    base.update(kw)
    return Vacancy(**base)


@pytest.fixture
def cfg():
    return FilterConfig()


def test_salary_from_above_threshold_passes(cfg):
    assert is_relevant(V(salary_from=45000), cfg)


def test_salary_from_exactly_threshold_passes(cfg):
    assert is_relevant(V(salary_from=40000), cfg)


def test_salary_from_below_threshold_dropped(cfg):
    assert not is_relevant(V(salary_from=39999), cfg)


def test_salary_only_to_above_threshold_passes(cfg):
    assert is_relevant(V(salary_from=None, salary_to=50000), cfg)


def test_salary_only_to_below_threshold_dropped(cfg):
    assert not is_relevant(V(salary_from=None, salary_to=30000), cfg)


def test_salary_unknown_is_kept(cfg):
    assert is_relevant(V(salary_from=None, salary_to=None), cfg)


def test_salary_from_low_but_to_high_dropped(cfg):
    # правило ТЗ: смотрим salary_from, если он указан
    assert not is_relevant(V(salary_from=30000, salary_to=60000), cfg)


def test_experience_no_experience_passes(cfg):
    assert is_relevant(V(experience="Без опыта"), cfg)


def test_experience_from_one_year_passes(cfg):
    assert is_relevant(V(experience="От 1 года", salary_from=50000), cfg)


def test_experience_from_three_years_dropped(cfg):
    assert not is_relevant(V(experience="От 3 лет", salary_from=50000), cfg)


def test_experience_unknown_kept(cfg):
    assert is_relevant(V(experience=None), cfg)


def test_office_in_omsk_passes(cfg):
    assert is_relevant(V(city="Омск", salary_from=50000), cfg)


def test_office_in_novosibirsk_dropped(cfg):
    assert not is_relevant(V(city="Новосибирск", salary_from=50000), cfg)


def test_remote_from_other_city_passes(cfg):
    assert is_relevant(V(city="Новосибирск", is_remote=True, salary_from=50000), cfg)


def test_stop_word_flags_but_keeps(cfg):
    v = V(title="Менеджер по продажам", salary_from=50000)
    assert is_relevant(v, cfg)
    flags = find_flags(v, cfg.stop_words)
    assert "продаж" in flags


def test_no_stop_words_no_flags(cfg):
    assert find_flags(V(title="Оператор связи", salary_from=50000), cfg.stop_words) == []


def test_excluded_company_dropped(cfg):
    cfg.exclude_companies = ("Пятёрочка",)
    assert not is_relevant(V(company="Пятёрочка", salary_from=50000), cfg)


def test_drop_word_removes_vacancy(cfg):
    assert not is_relevant(
        V(title="Военнослужащий по контракту", salary_from=3_100_000), cfg
    )


def test_drop_word_in_description_removes_vacancy(cfg):
    assert not is_relevant(
        V(title="Оператор", description="Работа вахтовый метод, 60/30", salary_from=90000), cfg
    )
