from jobhunt.db import DB, UserSettings
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
    db.mark_sent(["superjob:1"], user_id=10)
    left = db.unsent(user_id=10)
    assert [v.key for v in left] == ["superjob:2"]


def test_unsent_is_per_user(tmp_path):
    db = DB(tmp_path / "t.db")
    db.upsert(V("superjob:1"))
    db.mark_sent(["superjob:1"], user_id=10)
    assert len(db.unsent(user_id=11)) == 1


def test_sent_vacancies_table_has_requested_columns(tmp_path):
    db = DB(tmp_path / "t.db")
    columns = {
        row[1] for row in db.conn.execute("PRAGMA table_info(sent_vacancies)")
    }
    assert {"user_id", "vacancy_id"} <= columns


def test_old_sent_rows_are_migrated(tmp_path):
    import sqlite3

    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE sent (
          vacancy_key TEXT NOT NULL,
          chat_id     INTEGER NOT NULL,
          kind        TEXT NOT NULL,
          sent_at     TEXT NOT NULL,
          PRIMARY KEY (vacancy_key, chat_id, kind)
        );
        INSERT INTO sent VALUES ('superjob:1', 10, 'digest', '2026-11-01T00:00:00+00:00');
        """
    )
    conn.commit()
    conn.close()

    db = DB(path)
    assert db.unsent(user_id=10) == []
    db.upsert(V("superjob:2"))
    assert [v.key for v in db.unsent(user_id=10)] == ["superjob:2"]


def test_red_flags_persisted(tmp_path):
    db = DB(tmp_path / "t.db")
    v = V()
    v.red_flags = ["продаж"]
    db.upsert(v)
    assert db.all()[0].red_flags == ["продаж"]


def test_mark_sent_twice_is_safe(tmp_path):
    db = DB(tmp_path / "t.db")
    db.upsert(V("superjob:1"))
    db.mark_sent(["superjob:1"], user_id=10)
    db.mark_sent(["superjob:1"], user_id=10)
    assert db.unsent(user_id=10) == []


def test_coordinates_persisted(tmp_path):
    db = DB(tmp_path / "t.db")
    v = V()
    v.lat = 54.99
    v.lng = 73.37
    db.upsert(v)
    stored = db.all()[0]
    assert stored.lat == 54.99
    assert stored.lng == 73.37


def test_user_settings_absent_by_default(tmp_path):
    db = DB(tmp_path / "t.db")
    assert db.get_user_settings(42) is None
    assert db.has_user_settings(42) is False


def test_user_settings_roundtrip(tmp_path):
    db = DB(tmp_path / "t.db")
    prefs = UserSettings(
        user_id=42,
        city="Омск",
        remote=True,
        stop_words=("стройк", "курьер"),
        job_types=("it", "logistics"),
        min_salary=55000,
    )
    db.save_user_settings(prefs)
    assert db.has_user_settings(42) is True
    assert db.get_user_settings(42) == prefs


def test_user_settings_job_types_default_empty(tmp_path):
    db = DB(tmp_path / "t.db")
    db.save_user_settings(UserSettings(user_id=7))
    assert db.get_user_settings(7).job_types == ()


def test_delete_user_settings_removes_row(tmp_path):
    db = DB(tmp_path / "t.db")
    db.save_user_settings(UserSettings(user_id=42, min_salary=55000))
    db.delete_user_settings(42)
    assert db.get_user_settings(42) is None
    assert db.has_user_settings(42) is False


def test_user_settings_update_keeps_one_row(tmp_path):
    db = DB(tmp_path / "t.db")
    db.save_user_settings(UserSettings(user_id=42, min_salary=40000))
    db.save_user_settings(UserSettings(user_id=42, min_salary=80000, remote=True))
    stored = db.get_user_settings(42)
    assert stored.min_salary == 80000
    assert stored.remote is True
    rows = db.conn.execute("SELECT COUNT(*) FROM user_settings").fetchone()[0]
    assert rows == 1


def test_user_settings_remote_only_without_city(tmp_path):
    db = DB(tmp_path / "t.db")
    db.save_user_settings(UserSettings(user_id=7, city=None, remote=True))
    stored = db.get_user_settings(7)
    assert stored.city is None
    assert stored.remote is True


def test_digest_is_enabled_by_default(tmp_path):
    db = DB(tmp_path / "t.db")
    db.save_user_settings(UserSettings(user_id=7))
    assert db.get_user_settings(7).digest_enabled is True
    assert [prefs.user_id for prefs in db.digest_recipients()] == [7]


def test_digest_recipients_skip_disabled_and_unknown(tmp_path):
    db = DB(tmp_path / "t.db")
    db.save_user_settings(UserSettings(user_id=7))
    db.save_user_settings(UserSettings(user_id=8, digest_enabled=False))
    assert [prefs.user_id for prefs in db.digest_recipients()] == [7]
    db.set_digest_enabled(7, False)
    assert db.digest_recipients() == []
    assert db.get_user_settings(7).digest_enabled is False


def test_digest_enabled_flag_survives_resave(tmp_path):
    db = DB(tmp_path / "t.db")
    db.save_user_settings(UserSettings(user_id=7, digest_enabled=False))
    db.save_user_settings(UserSettings(user_id=7, min_salary=80000, digest_enabled=False))
    stored = db.get_user_settings(7)
    assert stored.digest_enabled is False
    assert stored.min_salary == 80000


def test_old_user_settings_get_digest_column(tmp_path):
    import sqlite3

    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE user_settings (
          user_id    INTEGER PRIMARY KEY,
          city       TEXT,
          remote     INTEGER NOT NULL DEFAULT 0,
          stop_words TEXT NOT NULL DEFAULT '[]',
          min_salary INTEGER NOT NULL DEFAULT 40000,
          updated_at TEXT NOT NULL
        );
        INSERT INTO user_settings (user_id, city, remote, stop_words, min_salary, updated_at)
        VALUES (7, 'Омск', 0, '[]', 40000, '2026-11-01T00:00:00+00:00');
        """
    )
    conn.commit()
    conn.close()

    db = DB(path)
    assert db.get_user_settings(7).digest_enabled is True


def test_old_user_settings_get_job_types_column(tmp_path):
    import sqlite3

    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE user_settings (
          user_id        INTEGER PRIMARY KEY,
          city           TEXT,
          remote         INTEGER NOT NULL DEFAULT 0,
          stop_words     TEXT NOT NULL DEFAULT '[]',
          min_salary     INTEGER NOT NULL DEFAULT 40000,
          digest_enabled INTEGER NOT NULL DEFAULT 1,
          updated_at     TEXT NOT NULL
        );
        INSERT INTO user_settings VALUES (7, 'Омск', 0, '[]', 40000, 1, '2026-11-01T00:00:00+00:00');
        """
    )
    conn.commit()
    conn.close()

    db = DB(path)
    prefs = db.get_user_settings(7)
    assert prefs.job_types == ()
    db.save_user_settings(UserSettings(user_id=7, job_types=("it",)))
    assert db.get_user_settings(7).job_types == ("it",)


def test_add_donation_stores_payment(tmp_path):
    db = DB(tmp_path / "d.db")
    db.add_donation(7, 100, "charge-1")
    row = db.conn.execute(
        "SELECT user_id, amount, telegram_payment_charge_id, created_at FROM donations"
    ).fetchone()
    db.close()
    assert row["user_id"] == 7
    assert row["amount"] == 100
    assert row["telegram_payment_charge_id"] == "charge-1"
    assert row["created_at"]


def test_add_donation_ignores_repeated_charge(tmp_path):
    db = DB(tmp_path / "d.db")
    db.add_donation(7, 50, "charge-1")
    db.add_donation(7, 50, "charge-1")
    db.add_donation(8, 500, "charge-2")
    count, total = db.donations_total()
    db.close()
    assert count == 2
    assert total == 550
