from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StorageKey

SCHEMA = """
CREATE TABLE IF NOT EXISTS fsm_state (
  key   TEXT PRIMARY KEY,
  state TEXT,
  data  TEXT NOT NULL DEFAULT '{}'
);
"""


class SQLiteStorage(BaseStorage):
    """FSM-состояния в SQLite: онбординг переживает перезапуск бота."""

    def __init__(self, path: str | Path = "fsm.db"):
        self.conn = sqlite3.connect(str(path))
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    @staticmethod
    def _key(key: StorageKey) -> str:
        return f"{key.bot_id}:{key.chat_id}:{key.user_id}:{key.destiny}"

    async def set_state(self, key: StorageKey, state: State | str | None = None) -> None:
        value = state.state if isinstance(state, State) else state
        self.conn.execute(
            "INSERT INTO fsm_state (key, state, data) VALUES (?, ?, '{}') "
            "ON CONFLICT(key) DO UPDATE SET state = excluded.state",
            (self._key(key), value),
        )
        self.conn.commit()

    async def get_state(self, key: StorageKey) -> str | None:
        row = self.conn.execute(
            "SELECT state FROM fsm_state WHERE key = ?", (self._key(key),)
        ).fetchone()
        return row[0] if row else None

    async def set_data(self, key: StorageKey, data: dict[str, Any]) -> None:
        self.conn.execute(
            "INSERT INTO fsm_state (key, state, data) VALUES (?, NULL, ?) "
            "ON CONFLICT(key) DO UPDATE SET data = excluded.data",
            (self._key(key), json.dumps(data, ensure_ascii=False, default=str)),
        )
        self.conn.commit()

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        row = self.conn.execute(
            "SELECT data FROM fsm_state WHERE key = ?", (self._key(key),)
        ).fetchone()
        if row is None:
            return {}
        try:
            loaded = json.loads(row[0] or "{}")
        except ValueError:
            return {}
        return loaded if isinstance(loaded, dict) else {}

    async def close(self) -> None:
        self.conn.close()
