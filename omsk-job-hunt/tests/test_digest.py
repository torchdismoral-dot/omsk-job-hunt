import asyncio

from jobhunt.bot.digest import pick, send_digest, send_digests
from jobhunt.config import Settings
from jobhunt.db import DB, UserSettings
from jobhunt.normalize import Vacancy


def V(n: int, **kw):
    base = dict(
        key=f"superjob:{n}",
        source="superjob",
        source_id=str(n),
        title=f"Вакансия {n}",
        company="ООО",
        salary_from=50000,
        currency="RUB",
        city="Омск",
        url=f"https://example.org/{n}",
        published_at=f"2026-11-{n:02d}",
    )
    base.update(kw)
    return Vacancy(**base)


class FakeBot:
    def __init__(self):
        self.messages = []

    async def send_message(self, chat_id, text, **kw):
        self.messages.append((chat_id, text))


def test_digest_recipients_are_users_with_settings():
    db = DB(":memory:")
    db.save_user_settings(UserSettings(user_id=42))
    db.save_user_settings(UserSettings(user_id=43, digest_enabled=False))
    assert [prefs.user_id for prefs in db.digest_recipients()] == [42]


def test_pick_returns_newest_unsent():
    db = DB(":memory:")
    for n in (1, 2, 3):
        db.upsert(V(n))
    chosen = pick(db, Settings(), user_id=42, limit=2)
    assert [v.source_id for v in chosen] == ["3", "2"]


def test_send_digest_marks_sent_and_is_silent_twice():
    db = DB(":memory:")
    for n in (1, 2):
        db.upsert(V(n))
    bot = FakeBot()
    settings = Settings()

    first = asyncio.run(send_digest(bot, db, settings, 42))
    assert first == 2
    assert len(bot.messages) == 1
    assert "Вакансия 1" in bot.messages[0][1]

    second = asyncio.run(send_digest(bot, db, settings, 42))
    assert second == 0
    assert len(bot.messages) == 1


def test_send_digest_respects_limit():
    db = DB(":memory:")
    for n in range(1, 11):
        db.upsert(V(n))
    bot = FakeBot()
    sent = asyncio.run(send_digest(bot, db, Settings(), 42, limit=3))
    assert sent == 3
    assert len(db.unsent(42)) == 7


def test_sent_for_one_chat_does_not_hide_from_another():
    db = DB(":memory:")
    db.upsert(V(1))
    asyncio.run(send_digest(FakeBot(), db, Settings(), 42))
    assert len(db.unsent(99)) == 1


def test_send_digests_goes_only_to_enabled_users():
    db = DB(":memory:")
    db.upsert(V(1))
    db.save_user_settings(UserSettings(user_id=42))
    db.save_user_settings(UserSettings(user_id=43, digest_enabled=False))
    bot = FakeBot()
    total = asyncio.run(send_digests(bot, db, Settings()))
    assert total == 1
    assert bot.messages[0][0] == 42


def test_send_digests_skips_users_without_settings():
    db = DB(":memory:")
    db.upsert(V(1))
    assert asyncio.run(send_digests(FakeBot(), db, Settings())) == 0


def test_digest_job_refreshes_and_sends(tmp_path):
    from jobhunt.bot.app import digest_job

    path = str(tmp_path / "t.db")
    db = DB(path)
    db.save_user_settings(UserSettings(user_id=42))
    db.close()

    def fake_refresh(settings, db):
        db.upsert(V(1))
        return {"total": 1}

    bot = FakeBot()
    sent = asyncio.run(digest_job(bot, Settings(), path, refresh_fn=fake_refresh))
    assert sent == 1
    assert "Вакансия 1" in bot.messages[0][1]


def test_digest_job_survives_failed_refresh(tmp_path):
    from jobhunt.bot.app import digest_job

    path = str(tmp_path / "t.db")
    db = DB(path)
    db.upsert(V(1))
    db.save_user_settings(UserSettings(user_id=42))
    db.close()

    def broken_refresh(settings, db):
        raise RuntimeError("SuperJob недоступен")

    bot = FakeBot()
    sent = asyncio.run(digest_job(bot, Settings(), path, refresh_fn=broken_refresh))
    assert sent == 1


def test_refresh_job_returns_stats(tmp_path):
    from jobhunt.bot.app import refresh_job

    path = str(tmp_path / "t.db")
    DB(path).close()

    def fake_refresh(settings, db):
        return {"fetched": 3, "fresh": 1}

    stats = asyncio.run(refresh_job(Settings(), path, refresh_fn=fake_refresh))
    assert stats == {"fetched": 3, "fresh": 1}


def test_refresh_job_swallows_errors(tmp_path):
    from jobhunt.bot.app import refresh_job

    path = str(tmp_path / "t.db")
    DB(path).close()

    def broken(settings, db):
        raise RuntimeError("нет сети")

    assert asyncio.run(refresh_job(Settings(), path, refresh_fn=broken)) is None
