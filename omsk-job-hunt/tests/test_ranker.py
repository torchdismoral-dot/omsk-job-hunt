from jobhunt.normalize import Vacancy
from jobhunt.ranker import by_date, by_distance, by_salary, distance_rank


def V(**kw):
    base = dict(
        key="superjob:1",
        source="superjob",
        source_id="1",
        title="Оператор",
        company="ООО",
        salary_from=50000,
        salary_to=None,
        currency="RUB",
        city="Омск",
        district=None,
        is_remote=False,
        experience="Без опыта",
        url="https://example.org/1",
        published_at="2026-11-25",
    )
    base.update(kw)
    return Vacancy(**base)


def test_by_date_newest_first():
    a = V(key="a", published_at="2026-11-01")
    b = V(key="b", published_at="2026-11-25")
    c = V(key="c", published_at="2026-11-10")
    assert [v.key for v in by_date([a, b, c])] == ["b", "c", "a"]


def test_by_date_missing_date_last():
    a = V(key="a", published_at=None)
    b = V(key="b", published_at="2026-11-01")
    assert [v.key for v in by_date([a, b])] == ["b", "a"]


def test_by_salary_desc_and_none_last():
    low = V(key="low", salary_from=50000)
    high = V(key="high", salary_from=90000)
    unknown = V(key="unknown", salary_from=None)
    assert [v.key for v in by_salary([unknown, low, high])] == ["high", "low", "unknown"]


def test_distance_rank():
    assert distance_rank(V(district="Кировский")) == 0
    assert distance_rank(V(district="Центральный")) == 1
    assert distance_rank(V(district=None)) == 2
    assert distance_rank(V(district=None, is_remote=True)) == 3


def test_by_distance_order():
    remote = V(key="remote", is_remote=True)
    other = V(key="other")
    center = V(key="center", district="Центральный")
    kirov = V(key="kirov", district="Кировский")
    assert [v.key for v in by_distance([remote, other, center, kirov])] == [
        "kirov",
        "center",
        "other",
        "remote",
    ]


def test_by_distance_uses_coordinates():
    near = V(key="near", lat=54.9900, lng=73.3700)
    far = V(key="far", lat=55.1500, lng=73.7000)
    home = (54.9893, 73.3682)
    assert [v.key for v in by_distance([far, near], home=home)] == ["near", "far"]


def test_by_distance_puts_remote_last_even_if_close():
    remote = V(key="remote", is_remote=True, lat=54.9893, lng=73.3682)
    near = V(key="near", lat=54.9893, lng=73.3682)
    assert [v.key for v in by_distance([remote, near], home=(54.9893, 73.3682))] == [
        "near",
        "remote",
    ]


def test_by_distance_without_coordinates_goes_after_known_ones():
    unknown = V(key="unknown")
    near = V(key="near", lat=54.9900, lng=73.3700)
    home = (54.9893, 73.3682)
    assert [v.key for v in by_distance([unknown, near], home=home)] == ["near", "unknown"]


def test_haversine_is_sane():
    from jobhunt.ranker import haversine_km

    # Омск — Москалёнки, ~59 км по прямой
    assert 55 < haversine_km(54.9893, 73.3682, 54.9400, 72.4500) < 62


def test_rank_collapses_repeated_vacancies():
    from jobhunt.ranker import rank

    copies = [
        V(key=f"superjob:{i}", source_id=str(i), title="Учитель математики", company="Профи-центр")
        for i in range(5)
    ]
    assert len(rank(copies, "date")) == 1


def test_rank_keeps_different_salaries():
    from jobhunt.ranker import rank

    a = V(key="a", title="Менеджер", company="Билайн", salary_from=48000)
    b = V(key="b", title="Менеджер", company="Билайн", salary_from=60000)
    assert len(rank([a, b], "salary")) == 2


def test_rank_dedupe_keeps_newest_for_date_mode():
    from jobhunt.ranker import rank

    old = V(key="old", published_at="2026-11-01")
    new = V(key="new", published_at="2026-11-25")
    assert [v.key for v in rank([old, new], "date")] == ["new"]


def test_rank_dedupe_across_sources():
    from jobhunt.ranker import rank

    sj = V(key="superjob:1", source="superjob", title="Оператор", company="ООО Ромашка")
    tv = V(key="trudvsem:1", source="trudvsem", title="Оператор", company="ООО Ромашка")
    assert [v.source for v in rank([sj, tv], "date")] == ["superjob"]
