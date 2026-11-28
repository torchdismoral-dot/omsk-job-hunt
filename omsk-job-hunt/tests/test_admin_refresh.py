import asyncio
import threading
import time

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.types import Update

from jobhunt.bot import admin
from jobhunt.bot.admin import summary_text
from jobhunt.bot.handlers import build_router
from jobhunt.bot.messages import NO_ACCESS_TEXT, REFRESH_FAILED_TEXT, REFRESH_START_TEXT
from jobhunt.config import Settings
from jobhunt.db import DB

ADMIN_ID = 555
USER = {"id": ADMIN_ID, "is_bot": False, "first_name": "Алексей"}
STRANGER = {"id": 777, "is_bot": False, "first_name": "Чужой"}
CHAT = {"id": ADMIN_ID, "type": "private"}


class RecordingBot(Bot):
    def __init__(self):
        super().__init__(
            token="42:TEST",
            validate_token=False,
            default=DefaultBotProperties(parse_mode="HTML"),
        )
        self.sent: list[str] = []

    async def __call__(self, method, request_timeout=None):
        if type(method).__name__ == "SendMessage":
            self.sent.append(method.text)
            return None
        return True


def message_update(bot, update_id, text, user=USER):
    return Update.model_validate(
        {
            "update_id": update_id,
            "message": {
                "message_id": update_id,
                "date": int(time.time()),
                "chat": CHAT,
                "from": user,
                "text": text,
            },
        },
        context={"bot": bot},
    )


@pytest.fixture
def harness(tmp_path, monkeypatch):
    calls = []

    def fake_refresh(settings, db):
        db.conn.execute("SELECT COUNT(*) FROM vacancies").fetchone()  # соединение живо
        calls.append((settings, db, threading.get_ident()))
        return {"fetched": 10, "relevant": 5, "fresh": 3, "total": 211}

    monkeypatch.setattr(admin, "refresh", fake_refresh)
    bot = RecordingBot()
    db_path = str(tmp_path / "t.db")
    dispatcher = Dispatcher()
    dispatcher.include_router(build_router(Settings(admin_id=ADMIN_ID), db_path))
    return bot, dispatcher, db_path, calls


def run(bot, dispatcher, text, user=USER, update_id=1):
    return asyncio.run(dispatcher.feed_update(bot, message_update(bot, update_id, text, user)))


def test_stranger_gets_no_access_and_refresh_not_called(harness):
    bot, dispatcher, _, calls = harness
    run(bot, dispatcher, "/refresh", user=STRANGER)
    assert bot.sent == [NO_ACCESS_TEXT]
    assert calls == []


def test_without_admin_id_nobody_has_access(harness, tmp_path, monkeypatch):
    bot = RecordingBot()
    dispatcher = Dispatcher()
    dispatcher.include_router(build_router(Settings(admin_id=None), str(tmp_path / "x.db")))
    run(bot, dispatcher, "/refresh", user=STRANGER)
    assert bot.sent == [NO_ACCESS_TEXT]


def test_admin_sees_start_and_summary(harness):
    bot, dispatcher, _, calls = harness
    run(bot, dispatcher, "/refresh")
    assert bot.sent == [
        REFRESH_START_TEXT,
        "Сбор завершен! Добавлено новых вакансий: 3. Всего в базе: 211",
    ]
    assert len(calls) == 1


def test_refresh_uses_configured_db(harness):
    bot, dispatcher, db_path, calls = harness
    run(bot, dispatcher, "/refresh")
    _, db, _ = calls[0]
    assert isinstance(db, DB)
    assert db.path == db_path


def test_refresh_does_not_block_event_loop(harness):
    bot, dispatcher, _, calls = harness
    loop_thread = threading.get_ident()
    run(bot, dispatcher, "/refresh")
    assert calls[0][2] != loop_thread, "сбор должен идти в отдельном потоке"


def test_refresh_failure_is_reported(tmp_path, monkeypatch):
    def boom(settings, db):
        raise RuntimeError("SuperJob недоступен")

    monkeypatch.setattr(admin, "refresh", boom)
    bot = RecordingBot()
    dispatcher = Dispatcher()
    dispatcher.include_router(build_router(Settings(admin_id=ADMIN_ID), str(tmp_path / "t.db")))
    run(bot, dispatcher, "/refresh")
    assert bot.sent == [REFRESH_START_TEXT, REFRESH_FAILED_TEXT]


def test_summary_text_without_hh_keys_is_unchanged():
    stats = {"fetched": 10, "relevant": 5, "fresh": 3, "total": 211}
    assert summary_text(stats) == (
        "Сбор завершен! Добавлено новых вакансий: 3. Всего в базе: 211"
    )


def test_summary_text_mentions_hh_when_collected():
    stats = {"fresh": 3, "total": 211, "hh_fetched": 120}
    assert "Собрано с hh.ru: 120" in summary_text(stats)


def test_summary_text_warns_when_hh_blocked():
    stats = {"fresh": 1, "total": 5, "hh_fetched": 0, "hh_error": "hh: HTTP 403"}
    text = summary_text(stats)
    assert "Собрано с hh.ru: 0" in text
    assert "⚠️ hh: HTTP 403" in text


def test_admin_sees_hh_counters(tmp_path, monkeypatch):
    def fake_refresh(settings, db):
        return {"fetched": 20, "relevant": 15, "fresh": 7, "total": 300, "hh_fetched": 12}

    monkeypatch.setattr(admin, "refresh", fake_refresh)
    bot = RecordingBot()
    dispatcher = Dispatcher()
    dispatcher.include_router(build_router(Settings(admin_id=ADMIN_ID), str(tmp_path / "t.db")))
    run(bot, dispatcher, "/refresh")
    assert "Собрано с hh.ru: 12" in bot.sent[-1]

