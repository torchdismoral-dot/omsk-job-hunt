from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .normalize import Vacancy

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

CREATE TABLE IF NOT EXISTS sent (
  vacancy_key TEXT NOT NULL,
  chat_id     INTEGER NOT NULL,
  kind        TEXT NOT NULL,
  sent_at     TEXT NOT NULL,
  PRIMARY KEY (vacancy_key, chat_id, kind)
);

CREATE TABLE IF NOT EXISTS subscriptions (
  chat_id    INTEGER PRIMARY KEY,
  created_at TEXT NOT NULL,
  active     INTEGER NOT NULL DEFAULT 1
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

    def unsent(self, chat_id: int) -> list[Vacancy]:
        rows = self.conn.execute(
            """SELECT * FROM vacancies
               WHERE key NOT IN (
                 SELECT vacancy_key FROM sent WHERE chat_id = ?
               )
               ORDER BY published_at DESC""",
            (chat_id,),
        ).fetchall()
        return [self._to_vacancy(row) for row in rows]

    def mark_sent(self, keys, chat_id: int, kind: str = "digest") -> None:
        now = _now()
        self.conn.executemany(
            "INSERT OR IGNORE INTO sent (vacancy_key, chat_id, kind, sent_at) "
            "VALUES (?, ?, ?, ?)",
            [(key, chat_id, kind, now) for key in keys],
        )
        self.conn.commit()

    def subscribe(self, chat_id: int) -> None:
        self.conn.execute(
            """INSERT INTO subscriptions (chat_id, created_at, active) VALUES (?, ?, 1)
               ON CONFLICT(chat_id) DO UPDATE SET active = 1""",
            (chat_id, _now()),
        )
        self.conn.commit()

    def unsubscribe(self, chat_id: int) -> None:
        self.conn.execute(
            "UPDATE subscriptions SET active = 0 WHERE chat_id = ?", (chat_id,)
        )
        self.conn.commit()

    def is_subscribed(self, chat_id: int) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM subscriptions WHERE chat_id = ? AND active = 1", (chat_id,)
        ).fetchone()
        return row is not None

    def subscribers(self) -> list[int]:
        rows = self.conn.execute(
            "SELECT chat_id FROM subscriptions WHERE active = 1 ORDER BY chat_id"
        ).fetchall()
        return [row["chat_id"] for row in rows]

    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM vacancies").fetchone()[0]

    def close(self) -> None:
        self.conn.close()
