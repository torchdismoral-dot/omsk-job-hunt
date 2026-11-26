import pytest

from jobhunt.config import FilterConfig
from jobhunt.db import UserSettings
from jobhunt.filters import (
    SPHERES,
    check_job_types,
    find_flags,
    is_relevant,
    matches_user,
)
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


def test_blue_collar_title_kept_for_sphere_filtering(cfg):
    # рабочие специальности больше не отсекаются при сборе — решает выбор сфер
    assert is_relevant(V(title="Мастер отделочных работ", salary_from=270000), cfg)


def test_cashier_title_removed(cfg):
    assert not is_relevant(V(title="Продавец-кассир", salary_from=44690), cfg)


def test_abroad_title_removed(cfg):
    assert not is_relevant(V(title="Машинист бетононасоса (Египет)", salary_from=200000), cfg)


def test_blue_collar_word_in_description_does_not_drop_office_job(cfg):
    v = V(
        title="Специалист клиентского сервиса",
        company="Банк ВТБ (ПАО)",
        description="Обслуживание клиентов, оформление кредитов, работа с мастер-планом",
        salary_from=50100,
    )
    assert is_relevant(v, cfg)


def test_bank_cashier_kept(cfg):
    assert is_relevant(V(title="Кассир-операционист", company="Банк", salary_from=45000), cfg)


HOME = (54.9893, 73.3682)


def test_job_in_far_region_dropped(cfg):
    # Владивосток: SuperJob пишет «Омск», но координаты настоящие
    v = V(title="Электромеханик", lat=43.1155, lng=131.8855, salary_from=120000)
    assert not is_relevant(v, cfg, HOME)


def test_job_near_home_kept(cfg):
    assert is_relevant(V(salary_from=50000, lat=54.9900, lng=73.3700), cfg, HOME)


def test_far_remote_job_kept(cfg):
    v = V(is_remote=True, lat=43.1155, lng=131.8855, salary_from=120000)
    assert is_relevant(v, cfg, HOME)


def test_job_without_coordinates_kept(cfg):
    assert is_relevant(V(salary_from=50000), cfg, HOME)


def P(**kw):
    base = dict(
        user_id=1,
        city="Омск",
        remote=False,
        stop_words=(),
        job_types=(),
        min_salary=40000,
    )
    base.update(kw)
    return UserSettings(**base)


def test_user_omsk_choice_keeps_local_office():
    assert matches_user(V(salary_from=50000, city="Омск"), P())


def test_user_omsk_choice_drops_remote():
    assert not matches_user(V(city="Омск", is_remote=True, salary_from=50000), P())


def test_user_remote_choice_keeps_remote_only():
    prefs = P(city=None, remote=True)
    assert matches_user(V(city="Москва", is_remote=True, salary_from=50000), prefs)
    assert not matches_user(V(city="Омск", salary_from=50000), prefs)


def test_user_all_choice_keeps_omsk_and_remote():
    prefs = P(city="Омск", remote=True)
    assert matches_user(V(city="Омск", salary_from=50000), prefs)
    assert matches_user(V(city="Москва", is_remote=True, salary_from=50000), prefs)
    assert not matches_user(V(city="Новосибирск", salary_from=50000), prefs)


def test_user_stop_word_drops_vacancy():
    prefs = P(stop_words=("прораб",))
    assert not matches_user(V(title="Прораб на стройку", salary_from=60000), prefs)


def test_user_salary_threshold():
    prefs = P(min_salary=55000)
    assert not matches_user(V(salary_from=45000), prefs)
    assert matches_user(V(salary_from=55000), prefs)


def test_user_salary_unknown_kept():
    assert matches_user(V(salary_from=None, salary_to=None), P(min_salary=80000))


def test_user_salary_to_only():
    prefs = P(min_salary=55000)
    assert matches_user(V(salary_from=None, salary_to=60000), prefs)
    assert not matches_user(V(salary_from=None, salary_to=50000), prefs)


def test_sphere_labels_match_buttons():
    assert list(SPHERES) == [
        "banking", "it", "support", "admin", "sales", "logistics", "blue_collar",
    ]
    assert SPHERES["banking"][0] == "💼 Банки и финансы"
    assert SPHERES["it"][0] == "💻 IT и интернет"
    assert SPHERES["support"][0] == "📞 Клиентский сервис"
    assert SPHERES["admin"][0] == "🗂 Административный персонал"
    assert SPHERES["sales"][0] == "🛒 Продажи"
    assert SPHERES["logistics"][0] == "🚚 Логистика"
    assert SPHERES["blue_collar"][0] == "🛠 Рабочие"


def test_empty_spheres_keep_everything():
    assert check_job_types(V(title="Мастер отделочных работ"), ())


def test_sphere_mismatch_drops_vacancy():
    assert not check_job_types(V(title="Мастер отделочных работ"), ("it", "banking"))


def test_back_office_specialist_passes_banking():
    assert check_job_types(V(title="Специалист бэк-офиса"), ("banking",))


def test_chat_operator_passes_support():
    assert check_job_types(V(title="Оператор чата"), ("support",))


def test_any_selected_sphere_is_enough():
    assert check_job_types(V(title="Кладовщик"), ("it", "logistics"))


def test_sphere_matches_only_title_not_description():
    v = V(title="Специалист по документам", description="Работа в интернете, IT, системный админ")
    assert not check_job_types(v, ("it",))


def test_sphere_match_is_case_insensitive():
    assert check_job_types(V(title="СИСТЕМНЫЙ АДМИНИСТРАТОР"), ("it",))
    assert check_job_types(V(title="Бухгалтер"), ("banking",))


def test_unknown_sphere_key_matches_nothing():
    assert not check_job_types(V(title="Оператор"), ("unknown",))


def test_user_spheres_drop_before_stop_words():
    prefs = P(job_types=("it",))
    assert not matches_user(V(title="Менеджер по продажам", salary_from=50000), prefs)
    assert matches_user(V(title="Тестировщик ПО", salary_from=50000), prefs)


def test_user_sphere_selected_and_stop_word_still_drops():
    prefs = P(job_types=("sales",), stop_words=("продаж",))
    assert not matches_user(V(title="Менеджер по продажам", salary_from=50000), prefs)


def test_widened_sales_matches_store_admin_and_director():
    assert check_job_types(V(title="Администратор магазина"), ("sales",))
    assert check_job_types(V(title="Директор магазина-партнёр"), ("sales",))


def test_widened_support_matches_vip_and_personal_service():
    assert check_job_types(V(title="Менеджер по работе с VIP-клиентами"), ("support",))
    assert check_job_types(V(title="Менеджер по обслуживанию физических лиц"), ("support",))


def test_widened_admin_matches_document_flow():
    assert check_job_types(V(title="Специалист по документообороту"), ("admin",))


def test_widened_blue_collar_and_logistics():
    assert check_job_types(V(title="Мастер отделочных работ"), ("blue_collar",))
    assert check_job_types(V(title="Пеший курьер"), ("logistics",))
    assert check_job_types(V(title="Слесарь-ремонтник"), ("blue_collar",))
