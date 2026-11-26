import asyncio

from aiogram.fsm.storage.base import StorageKey

from jobhunt.bot.onboarding import Onboarding
from jobhunt.bot.storage import SQLiteStorage

KEY = StorageKey(bot_id=1, chat_id=7, user_id=7)


def test_state_and_data_survive_restart(tmp_path):
    path = tmp_path / "fsm.db"
    storage = SQLiteStorage(path)
    asyncio.run(storage.set_state(KEY, Onboarding.stop_words))
    asyncio.run(storage.set_data(KEY, {"stop_words": ["продаж"], "city": "Омск"}))
    asyncio.run(storage.close())

    reopened = SQLiteStorage(path)
    assert asyncio.run(reopened.get_state(KEY)) == "Onboarding:stop_words"
    assert asyncio.run(reopened.get_data(KEY)) == {"stop_words": ["продаж"], "city": "Омск"}
    asyncio.run(reopened.close())


def test_state_and_data_do_not_clobber_each_other(tmp_path):
    storage = SQLiteStorage(tmp_path / "fsm.db")
    asyncio.run(storage.set_data(KEY, {"city": "Омск"}))
    asyncio.run(storage.set_state(KEY, Onboarding.salary))
    assert asyncio.run(storage.get_state(KEY)) == "Onboarding:salary"
    assert asyncio.run(storage.get_data(KEY)) == {"city": "Омск"}
    asyncio.run(storage.close())


def test_different_users_are_isolated(tmp_path):
    storage = SQLiteStorage(tmp_path / "fsm.db")
    other = StorageKey(bot_id=1, chat_id=8, user_id=8)
    asyncio.run(storage.set_state(KEY, Onboarding.location))
    assert asyncio.run(storage.get_state(other)) is None
    assert asyncio.run(storage.get_data(other)) == {}
    asyncio.run(storage.close())


def test_cleared_state_is_none(tmp_path):
    storage = SQLiteStorage(tmp_path / "fsm.db")
    asyncio.run(storage.set_state(KEY, Onboarding.location))
    asyncio.run(storage.set_state(KEY, None))
    assert asyncio.run(storage.get_state(KEY)) is None
    asyncio.run(storage.close())
