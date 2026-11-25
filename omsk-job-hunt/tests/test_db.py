from jobhunt.db import DB
from jobhunt.normalize import Vacancy


def V(key="superjob:1", **kw):
    base = dict(
        key=key,
        source="superjob",
        source_id=key.split(":")[1],
        title="Оператор",
        company="ООО",
        salary_from=50000,
        salary_to=None,
        currency="RUB",
        city="Омск",
        district="Кировский",
        is_remote=False,
        experience="Без опыта",
        url="https://example.org/1",
        published_at="2026-11-25",
    )
    base.update(kw)
    return Vacancy(**base)


def test_first_upsert_is_new_second_is_not(tmp_path):
    db = DB(tmp_path / "t.db")
    assert db.upsert(V()) is True
    assert db.upsert(V()) is False


def test_vacancies_are_stored(tmp_path):
    db = DB(tmp_path / "t.db")
    db.upsert(V())
    stored = db.all()
    assert len(stored) == 1
    assert stored[0].title == "Оператор"
    assert stored[0].district == "Кировский"


def test_sent_is_excluded_from_unsent(tmp_path):
    db = DB(tmp_path / "t.db")
    db.upsert(V("superjob:1"))
    db.upsert(V("superjob:2", title="Пекарь"))
    db.mark_sent(["superjob:1"], chat_id=10)
    left = db.unsent(chat_id=10)
    assert [v.key for v in left] == ["superjob:2"]


def test_unsent_is_per_chat(tmp_path):
    db = DB(tmp_path / "t.db")
    db.upsert(V("superjob:1"))
    db.mark_sent(["superjob:1"], chat_id=10)
    assert len(db.unsent(chat_id=11)) == 1


def test_red_flags_persisted(tmp_path):
    db = DB(tmp_path / "t.db")
    v = V()
    v.red_flags = ["продаж"]
    db.upsert(v)
    assert db.all()[0].red_flags == ["продаж"]


def test_mark_sent_twice_is_safe(tmp_path):
    db = DB(tmp_path / "t.db")
    db.upsert(V("superjob:1"))
    db.mark_sent(["superjob:1"], chat_id=10)
    db.mark_sent(["superjob:1"], chat_id=10)
    assert db.unsent(chat_id=10) == []


def test_coordinates_persisted(tmp_path):
    db = DB(tmp_path / "t.db")
    v = V()
    v.lat = 54.99
    v.lng = 73.37
    db.upsert(v)
    stored = db.all()[0]
    assert stored.lat == 54.99
    assert stored.lng == 73.37
