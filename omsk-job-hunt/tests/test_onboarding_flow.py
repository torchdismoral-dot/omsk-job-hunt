import asyncio
import time

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Update

from jobhunt.bot.handlers import build_router
from jobhunt.bot.storage import SQLiteStorage
from jobhunt.config import Settings
from jobhunt.db import DB

USER = {"id": 777, "is_bot": False, "first_name": "Алексей"}
CHAT = {"id": 777, "type": "private"}


class RecordingBot(Bot):
    def __init__(self):
        super().__init__(
            token="42:TEST",
            validate_token=False,
            default=DefaultBotProperties(parse_mode="HTML"),
        )
        self.sent = []
        self.answers = []
        self.edits = []

    async def __call__(self, method, request_timeout=None):
        name = type(method).__name__
        if name == "SendMessage":
            self.sent.append((method.chat_id, method.text, method.reply_markup))
            return None
        if name == "AnswerCallbackQuery":
            self.answers.append(method.text)
            return True
        if name == "EditMessageReplyMarkup":
            self.edits.append(method.reply_markup)
            return True
        return True

    async def send_message(self, chat_id, text, **kwargs):
        self.sent.append((chat_id, text, kwargs.get("reply_markup")))

    async def answer_callback_query(self, callback_query_id, text=None, **kwargs):
        self.answers.append(text)

    async def delete_message(self, chat_id, message_id, **kwargs):
        return True


def make_dispatcher(tmp_path, fsm_path=None):
    db_path = str(tmp_path / "t.db")
    storage = SQLiteStorage(fsm_path) if fsm_path else MemoryStorage()
    dispatcher = Dispatcher(storage=storage)
    dispatcher.include_router(build_router(Settings(), db_path))
    return dispatcher, db_path


def message_update(bot, update_id, text):
    payload = {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "date": int(time.time()),
            "chat": CHAT,
            "from": USER,
            "text": text,
        },
    }
    return Update.model_validate(payload, context={"bot": bot})


def callback_update(bot, update_id, data):
    payload = {
        "update_id": update_id,
        "callback_query": {
            "id": str(update_id),
            "from": USER,
            "chat_instance": "test",
            "data": data,
            "message": {
                "message_id": update_id,
                "date": int(time.time()),
                "chat": CHAT,
                "from": {"id": 42, "is_bot": True, "first_name": "OmWork"},
                "text": "menu",
            },
        },
    }
    return Update.model_validate(payload, context={"bot": bot})


def test_new_user_full_onboarding(tmp_path):
    bot = RecordingBot()
    dispatcher, db_path = make_dispatcher(tmp_path)

    async def run():
        steps = [
            message_update(bot, 1, "/start"),
            callback_update(bot, 2, "ob:go"),
            callback_update(bot, 3, "ob:loc:all"),
            callback_update(bot, 4, "ob:jt:it"),
            callback_update(bot, 5, "ob:jt:logistics"),
            callback_update(bot, 6, "ob:jt:done"),
            callback_update(bot, 7, "ob:sw:sales"),
            callback_update(bot, 8, "ob:sw:done"),
            callback_update(bot, 9, "ob:sal:55000"),
        ]
        for update in steps:
            await dispatcher.feed_update(bot, update)

    asyncio.run(run())
    texts = [text for _, text, _ in bot.sent]
    assert "Настрою выдачу" in texts[0]
    assert any("Шаг 1 из 4" in text for text in texts)
    assert any("Шаг 2 из 4" in text for text in texts)
    assert any("Шаг 3 из 4" in text for text in texts)
    assert any("Шаг 4 из 4" in text for text in texts)
    final = texts[-1]
    assert "Настройки сохранены! Ищу: Омск и удалёнка" in "\n".join(texts)
    assert "сферы: 💻 IT и интернет, 🚚 Логистика" in "\n".join(texts)
    assert "ЗП от 55 000 ₽" in "\n".join(texts)
    assert "Продажи/Холодные звонки" in "\n".join(texts)
    assert final  # финальное сообщение не пустое

    db = DB(db_path)
    prefs = db.get_user_settings(777)
    db.close()
    assert prefs is not None
    assert prefs.city == "Омск"
    assert prefs.remote is True
    assert prefs.min_salary == 55000
    assert prefs.job_types == ("it", "logistics")
    assert "продаж" in prefs.stop_words


def test_known_user_gets_menu_and_settings_prefilled(tmp_path):
    bot = RecordingBot()
    dispatcher, db_path = make_dispatcher(tmp_path)
    db = DB(db_path)
    from jobhunt.db import UserSettings

    db.save_user_settings(
        UserSettings(
            user_id=777, city=None, remote=True, job_types=("it",), min_salary=80000
        )
    )
    db.close()

    async def run():
        await dispatcher.feed_update(bot, message_update(bot, 1, "/start"))
        await dispatcher.feed_update(bot, callback_update(bot, 2, "settings"))
        await dispatcher.feed_update(bot, callback_update(bot, 3, "ob:loc:omsk"))

    asyncio.run(run())
    texts = [text for _, text, _ in bot.sent]
    assert "С возвращением" in texts[0]
    menu = bot.sent[0][2]
    callbacks = [button.callback_data for row in menu.inline_keyboard for button in row]
    assert "settings" in callbacks
    assert any("Шаг 1 из 4" in text and "галочкой" in text for text in texts)
    location = bot.sent[1][2]
    marked = [button.text for row in location.inline_keyboard for button in row]
    assert "✅ Удалёнка" in marked
    spheres = [button.text for row in bot.sent[-1][2].inline_keyboard for button in row]
    assert "✅ 💻 IT и интернет" in spheres


def test_cancel_clears_state(tmp_path):
    bot = RecordingBot()
    dispatcher, db_path = make_dispatcher(tmp_path)

    async def run():
        await dispatcher.feed_update(bot, message_update(bot, 1, "/start"))
        await dispatcher.feed_update(bot, message_update(bot, 2, "/cancel"))

    asyncio.run(run())
    texts = [text for _, text, _ in bot.sent]
    assert any("Настройка отменена" in text for text in texts)
    db = DB(db_path)
    assert db.get_user_settings(777) is None
    db.close()


def test_custom_stop_words_are_parsed(tmp_path):
    bot = RecordingBot()
    dispatcher, db_path = make_dispatcher(tmp_path)

    async def run():
        await dispatcher.feed_update(bot, message_update(bot, 1, "/start"))
        await dispatcher.feed_update(bot, callback_update(bot, 2, "ob:go"))
        await dispatcher.feed_update(bot, callback_update(bot, 3, "ob:loc:remote"))
        await dispatcher.feed_update(bot, callback_update(bot, 4, "ob:jt:any"))
        await dispatcher.feed_update(bot, callback_update(bot, 5, "ob:jt:done"))
        await dispatcher.feed_update(bot, callback_update(bot, 6, "ob:sw:custom"))
        await dispatcher.feed_update(bot, message_update(bot, 7, "Курьер, вахта"))
        await dispatcher.feed_update(bot, callback_update(bot, 8, "ob:sw:done"))
        await dispatcher.feed_update(bot, callback_update(bot, 9, "ob:sal:40000"))

    asyncio.run(run())
    db = DB(db_path)
    prefs = db.get_user_settings(777)
    db.close()
    assert prefs.city is None
    assert prefs.remote is True
    assert prefs.job_types == ()
    assert prefs.stop_words == ("курьер", "вахта")


def test_spheres_any_clears_selection(tmp_path):
    bot = RecordingBot()
    dispatcher, db_path = make_dispatcher(tmp_path)

    async def run():
        await dispatcher.feed_update(bot, message_update(bot, 1, "/start"))
        await dispatcher.feed_update(bot, callback_update(bot, 2, "ob:go"))
        await dispatcher.feed_update(bot, callback_update(bot, 3, "ob:loc:omsk"))
        await dispatcher.feed_update(bot, callback_update(bot, 4, "ob:jt:it"))
        await dispatcher.feed_update(bot, callback_update(bot, 5, "ob:jt:any"))
        await dispatcher.feed_update(bot, callback_update(bot, 6, "ob:jt:done"))
        await dispatcher.feed_update(bot, callback_update(bot, 7, "ob:sw:none"))
        await dispatcher.feed_update(bot, callback_update(bot, 8, "ob:sw:done"))
        await dispatcher.feed_update(bot, callback_update(bot, 9, "ob:sal:40000"))

    asyncio.run(run())
    db = DB(db_path)
    assert db.get_user_settings(777).job_types == ()
    db.close()


def test_onboarding_survives_bot_restart(tmp_path):
    fsm_path = tmp_path / "fsm.db"
    bot = RecordingBot()
    first, _ = make_dispatcher(tmp_path, fsm_path)

    async def begin():
        await first.feed_update(bot, message_update(bot, 1, "/start"))
        await first.feed_update(bot, callback_update(bot, 2, "ob:go"))
        await first.feed_update(bot, callback_update(bot, 3, "ob:loc:all"))
        await first.storage.close()

    asyncio.run(begin())
    second, _ = make_dispatcher(tmp_path, fsm_path)
    asyncio.run(second.feed_update(bot, callback_update(bot, 4, "ob:jt:done")))
    asyncio.run(second.feed_update(bot, callback_update(bot, 5, "ob:sw:sales")))
    texts = [text for _, text, _ in bot.sent]
    assert any("Сейчас исключаю: Продажи/Холодные звонки" in text for text in texts)


def test_stale_onboarding_button_gets_hint(tmp_path):
    bot = RecordingBot()
    dispatcher, _ = make_dispatcher(tmp_path)
    asyncio.run(dispatcher.feed_update(bot, callback_update(bot, 1, "ob:sw:sales")))
    assert any("устарела" in (answer or "") for answer in bot.answers)


def test_reset_settings_deletes_prefs_and_restarts_onboarding(tmp_path):
    from jobhunt.db import UserSettings

    bot = RecordingBot()
    dispatcher, db_path = make_dispatcher(tmp_path)
    db = DB(db_path)
    db.save_user_settings(UserSettings(user_id=777, city=None, remote=True, min_salary=80000))
    db.close()

    async def run():
        await dispatcher.feed_update(bot, message_update(bot, 1, "/start"))
        await dispatcher.feed_update(bot, callback_update(bot, 2, "settings"))
        await dispatcher.feed_update(bot, callback_update(bot, 3, "settings:reset"))
        await dispatcher.feed_update(bot, callback_update(bot, 4, "ob:go"))

    asyncio.run(run())
    db = DB(db_path)
    assert db.get_user_settings(777) is None
    db.close()
    texts = [text for _, text, _ in bot.sent]
    assert any("Настройки сброшены" in text for text in texts)
    assert any("Шаг 1 из 4" in text for text in texts)


def test_empty_feed_is_sent_once_with_advice_and_settings_button(tmp_path):
    """База полна, но под фильтры ничего не подошло — совет про фильтры."""
    from jobhunt.db import UserSettings
    from jobhunt.normalize import Vacancy

    bot = RecordingBot()
    dispatcher, db_path = make_dispatcher(tmp_path)
    db = DB(db_path)
    db.save_user_settings(UserSettings(user_id=777))
    db.upsert(
        Vacancy(
            key="superjob:1",
            source="superjob",
            source_id="1",
            title="Оператор",
            company="ООО",
            salary_from=60000,
            currency="RUB",
            city="Москва",
            url="https://example.org/1",
            published_at="2026-11-25",
        )
    )
    db.close()

    async def run():
        await dispatcher.feed_update(bot, message_update(bot, 1, "/top"))
        await dispatcher.feed_update(bot, callback_update(bot, 2, "top:date"))

    asyncio.run(run())
    empty = [(text, markup) for _, text, markup in bot.sent if "пока пусто" in text]
    assert len(empty) == 1
    text, markup = empty[0]
    assert "По твоим фильтрам пока пусто 😔" in text
    assert "• Снизить минимальную ЗП (например, до 30 000 ₽)" in text
    assert "• Добавить сферы в ⚙️ Настройках" in text
    assert "• Заглянуть позже (база обновляется каждые 48 часов)" in text
    callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
    assert callbacks == ["settings"]


def test_empty_database_says_so_instead_of_blaming_filters(tmp_path):
    """Пустая база — это не «узкие фильтры»: текст должен вести себя иначе."""
    from jobhunt.db import UserSettings

    bot = RecordingBot()
    dispatcher, db_path = make_dispatcher(tmp_path)
    db = DB(db_path)
    db.save_user_settings(UserSettings(user_id=777))
    db.close()

    async def run():
        await dispatcher.feed_update(bot, callback_update(bot, 1, "top:salary"))

    asyncio.run(run())
    texts = [text for _, text, _ in bot.sent]
    assert any("База пока пустая" in text for text in texts)
    assert not any("По твоим фильтрам пока пусто" in text for text in texts)


def test_menu_shows_digest_state_and_toggle_turns_it_off(tmp_path):
    from jobhunt.db import UserSettings

    bot = RecordingBot()
    dispatcher, db_path = make_dispatcher(tmp_path)
    db = DB(db_path)
    db.save_user_settings(UserSettings(user_id=777))
    db.close()

    asyncio.run(dispatcher.feed_update(bot, message_update(bot, 1, "/start")))
    menu = bot.sent[0][2]
    labels = [button.text for row in menu.inline_keyboard for button in row]
    assert "🔔 Рассылка: вкл" in labels

    asyncio.run(dispatcher.feed_update(bot, callback_update(bot, 2, "digest:toggle")))
    db = DB(db_path)
    assert db.get_user_settings(777).digest_enabled is False
    db.close()
    edited = [button.text for row in bot.edits[-1].inline_keyboard for button in row]
    assert "🔕 Рассылка: выкл" in edited


def test_stop_digest_command_disables_and_enables(tmp_path):
    from jobhunt.db import UserSettings

    bot = RecordingBot()
    dispatcher, db_path = make_dispatcher(tmp_path)
    db = DB(db_path)
    db.save_user_settings(UserSettings(user_id=777))
    db.close()

    asyncio.run(dispatcher.feed_update(bot, message_update(bot, 1, "/stop_digest")))
    texts = [text for _, text, _ in bot.sent]
    assert any("Рассылка выключена" in text for text in texts)
    db = DB(db_path)
    assert db.get_user_settings(777).digest_enabled is False
    db.close()

    asyncio.run(dispatcher.feed_update(bot, message_update(bot, 2, "/stop_digest")))
    texts = [text for _, text, _ in bot.sent]
    assert any("Рассылка включена" in text for text in texts)
    db = DB(db_path)
    assert db.get_user_settings(777).digest_enabled is True
    db.close()


def test_stop_digest_without_settings_asks_to_start(tmp_path):
    bot = RecordingBot()
    dispatcher, _ = make_dispatcher(tmp_path)
    asyncio.run(dispatcher.feed_update(bot, message_update(bot, 1, "/stop_digest")))
    texts = [text for _, text, _ in bot.sent]
    assert any("/start" in text for text in texts)


def test_unsubscribe_disables_digest(tmp_path):
    from jobhunt.db import UserSettings

    bot = RecordingBot()
    dispatcher, db_path = make_dispatcher(tmp_path)
    db = DB(db_path)
    db.save_user_settings(UserSettings(user_id=777))
    db.close()

    asyncio.run(dispatcher.feed_update(bot, message_update(bot, 1, "/unsubscribe")))
    db = DB(db_path)
    assert db.get_user_settings(777).digest_enabled is False
    db.close()
