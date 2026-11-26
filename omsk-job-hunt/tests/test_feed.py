from jobhunt.bot.feed import load
from jobhunt.config import Settings
from jobhunt.db import DB, UserSettings
from jobhunt.normalize import Vacancy


def V(key, **kw):
    base = dict(
        key=key,
        source="superjob",
        source_id=key.split(":")[1],
        title="Оператор",
        company="ООО",
        salary_from=50000,
        currency="RUB",
        city="Омск",
        url=f"https://example.org/{key}",
        published_at="2026-11-25",
    )
    base.update(kw)
    return Vacancy(**base)


def make_db(tmp_path):
    db = DB(tmp_path / "t.db")
    db.upsert(V("s:1", title="Офис Омск", salary_from=60000))
    db.upsert(V("s:2", title="Удалёнка Москва", city="Москва", is_remote=True, salary_from=70000))
    db.upsert(V("s:3", title="Другой город", city="Новосибирск", salary_from=90000))
    db.upsert(V("s:4", title="Прораб на стройке", salary_from=80000))
    db.upsert(V("s:5", title="Офис дешёвый", salary_from=45000))
    return db


def test_load_filters_by_location(tmp_path):
    db = make_db(tmp_path)
    prefs = UserSettings(user_id=1, city="Омск", remote=False)
    titles = [v.title for v in load(db, Settings(), prefs, "date")]
    assert titles == ["Офис Омск", "Прораб на стройке", "Офис дешёвый"]


def test_load_filters_by_stop_words_and_salary(tmp_path):
    db = make_db(tmp_path)
    prefs = UserSettings(user_id=1, city="Омск", remote=True, stop_words=("прораб",), min_salary=55000)
    titles = [v.title for v in load(db, Settings(), prefs, "date")]
    assert titles == ["Офис Омск", "Удалёнка Москва"]


def test_load_without_prefs_returns_everything(tmp_path):
    db = make_db(tmp_path)
    assert len(load(db, Settings(), None, "date")) == 5
