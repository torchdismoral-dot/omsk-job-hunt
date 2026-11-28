from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .normalize import Vacancy


@dataclass
class UserSettings:
    user_id: int
    city: str | None = "Омск"
    remote: bool = False
    stop_words: tuple[str, ...] = ()
    job_types: tuple[str, ...] = ()
    min_salary: int = 40000
    digest_enabled: bool = True

SCHEMA = """
CREATE TABLE IF NOT EXISTS vacancies (
  key             TEXT PRIMARY KEY,
  source          TEXT NOT NULL,
  source_id       TEXT NOT NULL,
  title           TEXT NOT NULL,
  company         TEXT,
  salary_from     INTEGER,
  salary_to       INTEGER,
  currency        TEXT,
  city            TEXT,
  district        TEXT,
  is_remote       INTEGER NOT NULL DEFAULT 0,
  experience      TEXT,
  url             TEXT NOT NULL,
  published_at    TEXT,
  description     TEXT,
  lat             REAL,
  lng             REAL,
  first_seen_at   TEXT NOT NULL,
  last_seen_at    TEXT NOT NULL,
  red_flags       TEXT,
  raw             TEXT
);

CREATE TABLE IF NOT EXISTS sent_vacancies (
  user_id    INTEGER NOT NULL,
  vacancy_id TEXT NOT NULL,
  sent_at    TEXT NOT NULL,
  PRIMARY KEY (user_id, vacancy_id)
);

CREATE TABLE IF NOT EXISTS user_settings (
  user_id        INTEGER PRIMARY KEY,
  city           TEXT,
  remote         INTEGER NOT NULL DEFAULT 0,
  stop_words     TEXT NOT NULL DEFAULT '[]',
  job_types      TEXT NOT NULL DEFAULT '[]',
  min_salary     INTEGER NOT NULL DEFAULT 40000,
  digest_enabled INTEGER NOT NULL DEFAULT 1,
  updated_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS donations (
  id                        INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id                   INTEGER NOT NULL,
  amount                    INTEGER NOT NULL,
  telegram_payment_charge_id TEXT NOT NULL UNIQUE,
  created_at                TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at TEXT, finished_at TEXT,
  fetched INTEGER, fresh INTEGER, error TEXT
);
"""

FIELDS = (
    "key", "source", "source_id", "title", "company", "salary_from", "salary_to",
    "currency", "city", "district", "is_remote", "experience", "url",
    "published_at", "description", "lat", "lng",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _words(raw) -> tuple[str, ...]:
    try:
        values = json.loads(raw or "[]")
    except (TypeError, ValueError):
        return ()
    if not isinstance(values, list):
        return ()
    return tuple(str(word) for word in values)


PERSISTENCE_PREFIX = "/data/"


def persistence_warning(db_path: str, container: bool | None = None) -> str | None:
    """Текст предупреждения, если файл базы не на постоянном диске.

    Актуально только для Linux-контейнера: на Amvera каталог приложения
    пересоздаётся при каждой сборке, и база вне /data молча обнуляется после
    деплоя. На рабочей машине за относительным путём тоже может лежать база,
    поэтому там молчим.
    """
    if container is None:
        container = os.sep == "/"
    if not container:
        return None
    if db_path == ":memory:" or db_path.startswith(PERSISTENCE_PREFIX):
        return None
    return (
        f"JOBHUNT_DB={db_path!r}: база не в {PERSISTENCE_PREFIX} — файл сотрётся "
        "при пересборке образа, задай JOBHUNT_DB=/data/jobhunt.db"
    )


class DB:
    def __init__(self, path: str | Path = "jobhunt.db"):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self._migrate()
        self.conn.commit()

    def _migrate(self) -> None:
        """Догоняет схему базы, созданной прошлой версией."""
        have = {row[1] for row in self.conn.execute("PRAGMA table_info(vacancies)")}
        for column, decl in (("description", "TEXT"), ("lat", "REAL"), ("lng", "REAL")):
            if column not in have:
                self.conn.execute(f"ALTER TABLE vacancies ADD COLUMN {column} {decl}")

        settings_columns = {
            row[1] for row in self.conn.execute("PRAGMA table_info(user_settings)")
        }
        if "digest_enabled" not in settings_columns:
            self.conn.execute(
                "ALTER TABLE user_settings ADD COLUMN digest_enabled INTEGER NOT NULL DEFAULT 1"
            )
        if "job_types" not in settings_columns:
            self.conn.execute(
                "ALTER TABLE user_settings ADD COLUMN job_types TEXT NOT NULL DEFAULT '[]'"
            )

        sent_columns = {
            row[1] for row in self.conn.execute("PRAGMA table_info(sent)")
        }
        if sent_columns:
            self.conn.execute(
                """INSERT OR IGNORE INTO sent_vacancies (user_id, vacancy_id, sent_at)
                   SELECT chat_id, vacancy_key, sent_at FROM sent"""
            )

        run_columns = {row[1] for row in self.conn.execute("PRAGMA table_info(runs)")}
        for column, decl in (
            ("relevant", "INTEGER"),
            ("total", "INTEGER"),
            ("sources", "TEXT"),
        ):
            if column not in run_columns:
                self.conn.execute(f"ALTER TABLE runs ADD COLUMN {column} {decl}")

    def upsert(self, vacancy: Vacancy) -> bool:
        """True, если вакансия встретилась впервые."""
        exists = self.conn.execute(
            "SELECT 1 FROM vacancies WHERE key = ?", (vacancy.key,)
        ).fetchone()
        now = _now()
        flags = json.dumps(vacancy.red_flags, ensure_ascii=False)
        if exists:
            self.conn.execute(
                """UPDATE vacancies
                   SET last_seen_at = ?, red_flags = ?, salary_from = ?,
                       salary_to = ?, url = ?, description = ?, lat = ?, lng = ?
                   WHERE key = ?""",
                (now, flags, vacancy.salary_from, vacancy.salary_to,
                 vacancy.url, vacancy.description, vacancy.lat, vacancy.lng,
                 vacancy.key),
            )
            self.conn.commit()
            return False
        values = {
            "key": vacancy.key,
            "source": vacancy.source,
            "source_id": vacancy.source_id,
            "title": vacancy.title,
            "company": vacancy.company,
            "salary_from": vacancy.salary_from,
            "salary_to": vacancy.salary_to,
            "currency": vacancy.currency,
            "city": vacancy.city,
            "district": vacancy.district,
            "is_remote": int(vacancy.is_remote),
            "experience": vacancy.experience,
            "url": vacancy.url,
            "published_at": vacancy.published_at,
            "description": vacancy.description,
            "lat": vacancy.lat,
            "lng": vacancy.lng,
        }
        placeholders = ", ".join("?" for _ in FIELDS) + ", ?, ?, ?"
        self.conn.execute(
            f"INSERT INTO vacancies ({', '.join(FIELDS)}, first_seen_at, "
            f"last_seen_at, red_flags) VALUES ({placeholders})",
            [values[f] for f in FIELDS] + [now, now, flags],
        )
        self.conn.commit()
        return True

    def _to_vacancy(self, row: sqlite3.Row) -> Vacancy:
        return Vacancy(
            key=row["key"],
            source=row["source"],
            source_id=row["source_id"],
            title=row["title"],
            company=row["company"],
            salary_from=row["salary_from"],
            salary_to=row["salary_to"],
            currency=row["currency"] or "RUB",
            city=row["city"],
            district=row["district"],
            is_remote=bool(row["is_remote"]),
            experience=row["experience"],
            url=row["url"],
            published_at=row["published_at"],
            description=row["description"],
            lat=row["lat"],
            lng=row["lng"],
            red_flags=json.loads(row["red_flags"] or "[]"),
        )

    def all(self) -> list[Vacancy]:
        rows = self.conn.execute(
            "SELECT * FROM vacancies ORDER BY published_at DESC"
        ).fetchall()
        return [self._to_vacancy(row) for row in rows]

    def unsent(self, user_id: int) -> list[Vacancy]:
        rows = self.conn.execute(
            """SELECT * FROM vacancies
               WHERE key NOT IN (
                 SELECT vacancy_id FROM sent_vacancies WHERE user_id = ?
               )
               ORDER BY published_at DESC""",
            (user_id,),
        ).fetchall()
        return [self._to_vacancy(row) for row in rows]

    def mark_sent(self, keys, user_id: int) -> None:
        now = _now()
        self.conn.executemany(
            "INSERT OR IGNORE INTO sent_vacancies (user_id, vacancy_id, sent_at) "
            "VALUES (?, ?, ?)",
            [(user_id, key, now) for key in keys],
        )
        self.conn.commit()

    def set_digest_enabled(self, user_id: int, enabled: bool) -> None:
        self.conn.execute(
            "UPDATE user_settings SET digest_enabled = ?, updated_at = ? WHERE user_id = ?",
            (int(enabled), _now(), user_id),
        )
        self.conn.commit()

    def get_user_settings(self, user_id: int) -> UserSettings | None:
        row = self.conn.execute(
            "SELECT * FROM user_settings WHERE user_id = ?", (user_id,)
        ).fetchone()
        if row is None:
            return None
        return UserSettings(
            user_id=row["user_id"],
            city=row["city"],
            remote=bool(row["remote"]),
            stop_words=_words(row["stop_words"]),
            job_types=_words(row["job_types"]),
            min_salary=row["min_salary"],
            digest_enabled=bool(row["digest_enabled"]),
        )

    def save_user_settings(self, prefs: UserSettings) -> None:
        self.conn.execute(
            """INSERT INTO user_settings
                 (user_id, city, remote, stop_words, job_types, min_salary,
                  digest_enabled, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
                 city = excluded.city,
                 remote = excluded.remote,
                 stop_words = excluded.stop_words,
                 job_types = excluded.job_types,
                 min_salary = excluded.min_salary,
                 digest_enabled = excluded.digest_enabled,
                 updated_at = excluded.updated_at""",
            (
                prefs.user_id,
                prefs.city,
                int(prefs.remote),
                json.dumps(list(prefs.stop_words), ensure_ascii=False),
                json.dumps(list(prefs.job_types), ensure_ascii=False),
                prefs.min_salary,
                int(prefs.digest_enabled),
                _now(),
            ),
        )
        self.conn.commit()

    def has_user_settings(self, user_id: int) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM user_settings WHERE user_id = ?", (user_id,)
        ).fetchone()
        return row is not None

    def delete_user_settings(self, user_id: int) -> None:
        self.conn.execute("DELETE FROM user_settings WHERE user_id = ?", (user_id,))
        self.conn.commit()

    def digest_recipients(self) -> list[UserSettings]:
        """Все, кто прошёл онбординг и не отключил рассылку."""
        rows = self.conn.execute(
            "SELECT user_id FROM user_settings WHERE digest_enabled = 1 ORDER BY user_id"
        ).fetchall()
        recipients = []
        for row in rows:
            prefs = self.get_user_settings(row["user_id"])
            if prefs is not None:
                recipients.append(prefs)
        return recipients

    def add_donation(self, user_id: int, amount: int, charge_id: str) -> bool:
        """False, если платёж с таким charge_id уже записан (повтор от Telegram)."""
        cursor = self.conn.execute(
            """INSERT OR IGNORE INTO donations
                 (user_id, amount, telegram_payment_charge_id, created_at)
               VALUES (?, ?, ?, ?)""",
            (user_id, amount, charge_id, _now()),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def donations_total(self) -> tuple[int, int]:
        row = self.conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(amount), 0) FROM donations"
        ).fetchone()
        return row[0], row[1]

    def users_count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM user_settings").fetchone()[0]

    def count_by_source(self) -> dict[str, int]:
        rows = self.conn.execute(
            "SELECT source, COUNT(*) FROM vacancies GROUP BY source ORDER BY source"
        ).fetchall()
        return {row[0]: row[1] for row in rows}

    def record_run(self, stats: dict, started_at: str | None = None) -> None:
        """Пишет прогон в runs: по /stats видно, когда собирали и что упало."""
        errors = stats.get("errors") or {}
        if stats.get("hh_error"):
            errors.setdefault("hh", stats["hh_error"])
        sources = {
            name: stats.get(f"{name}_fetched")
            for name in ("superjob", "trudvsem", "hh")
            if f"{name}_fetched" in stats
        }
        self.conn.execute(
            """INSERT INTO runs
               (started_at, finished_at, fetched, fresh, error, relevant, total, sources)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                started_at or _now(),
                _now(),
                stats.get("fetched"),
                stats.get("fresh"),
                "; ".join(errors.values()) or None,
                stats.get("relevant"),
                stats.get("total"),
                json.dumps(sources, ensure_ascii=False),
            ),
        )
        self.conn.commit()

    def last_run(self) -> dict | None:
        row = self.conn.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 1").fetchone()
        return dict(row) if row else None

    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM vacancies").fetchone()[0]

    def close(self) -> None:
        self.conn.close()
