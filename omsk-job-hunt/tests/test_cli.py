from jobhunt.cli import format_vacancy
from jobhunt.normalize import Vacancy


def V(**kw):
    base = dict(key="superjob:1", source="superjob", source_id="1", title="Пекарь", url="https://e.org/1")
    base.update(kw)
    return Vacancy(**base)


def test_full_salary_range():
    text = format_vacancy(1, V(salary_from=45000, salary_to=60000))
    assert "45 000 – 60 000 ₽" in text


def test_salary_from_only():
    assert "от 45 000 ₽" in format_vacancy(1, V(salary_from=45000))


def test_salary_to_only():
    assert "до 60 000 ₽" in format_vacancy(1, V(salary_to=60000))


def test_equal_bounds_print_as_from():
    assert "от 45 000 ₽" in format_vacancy(1, V(salary_from=45000, salary_to=45000))


def test_unknown_salary():
    assert "зарплата не указана" in format_vacancy(1, V())


def test_date_formatted():
    assert "25.11" in format_vacancy(1, V(published_at="2026-11-25"))


def test_broken_date_is_safe():
    assert "дата неизвестна" in format_vacancy(1, V(published_at="2026"))


def test_remote_and_district_shown():
    assert "Кировский" in format_vacancy(1, V(district="Кировский"))
    assert "удалённо" in format_vacancy(1, V(is_remote=True))


def test_red_flags_printed():
    assert "⚑ продаж" in format_vacancy(1, V(red_flags=["продаж"]))
