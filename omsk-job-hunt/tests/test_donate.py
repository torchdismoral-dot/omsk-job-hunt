import asyncio
import time

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Update

from jobhunt.bot.handlers import build_router
from jobhunt.bot.keyboards import DONATION_STARS, main_menu_keyboard
from jobhunt.bot.messages import DONATE_TEXT, DONATION_THANKS
from jobhunt.config import Settings
from jobhunt.db import DB

USER = {"id": 777, "is_bot": False, "first_name": "Алексей"}
CHAT = {"id": 777, "type": "private"}


class PaymentBot(Bot):
    def __init__(self):
        super().__init__(
            token="42:TEST",
            validate_token=False,
            default=DefaultBotProperties(parse_mode="HTML"),
        )
        self.sent = []
        self.answers = []
        self.invoices = []
        self.checkouts = []

    async def __call__(self, method, request_timeout=None):
        name = type(method).__name__
        if name == "SendMessage":
            self.sent.append((method.chat_id, method.text, method.reply_markup))
            return None
        if name == "AnswerCallbackQuery":
            self.answers.append(method.text)
            return True
        if name == "SendInvoice":
            self.invoices.append(method)
            return None
        if name == "AnswerPreCheckoutQuery":
            self.checkouts.append(method)
            return True
        return True

    async def send_message(self, chat_id, text, **kwargs):
        self.sent.append((chat_id, text, kwargs.get("reply_markup")))

    async def answer_callback_query(self, callback_query_id, text=None, **kwargs):
        self.answers.append(text)

    async def delete_message(self, chat_id, message_id, **kwargs):
        return True


def make_bot(tmp_path):
    bot = PaymentBot()
    db_path = str(tmp_path / "t.db")
    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.include_router(build_router(Settings(), db_path))
    return bot, dispatcher, db_path


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


def pre_checkout_update(bot, update_id, amount=100, payload="donate"):
    payload_dict = {
        "update_id": update_id,
        "pre_checkout_query": {
            "id": str(update_id),
            "from": USER,
            "currency": "XTR",
            "total_amount": amount,
            "invoice_payload": payload,
        },
    }
    return Update.model_validate(payload_dict, context={"bot": bot})


def paid_update(bot, update_id, amount=100, charge_id="charge-1"):
    payload = {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "date": int(time.time()),
            "chat": CHAT,
            "from": USER,
            "successful_payment": {
                "currency": "XTR",
                "total_amount": amount,
                "invoice_payload": "donate",
                "telegram_payment_charge_id": charge_id,
                "provider_payment_charge_id": "provider-" + charge_id,
            },
        },
    }
    return Update.model_validate(payload, context={"bot": bot})


def test_main_menu_has_support_button():
    keyboard = main_menu_keyboard()
    buttons = [button for row in keyboard.inline_keyboard for button in row]
    donate = [button for button in buttons if button.callback_data == "donate"]
    assert len(donate) == 1
    assert "❤️ Поддержать проект" == donate[0].text


def test_donate_screen_has_exact_text_and_stars_buttons(tmp_path):
    bot, dispatcher, _ = make_bot(tmp_path)
    asyncio.run(dispatcher.feed_update(bot, callback_update(bot, 1, "donate")))
    _, text, markup = bot.sent[-1]
    assert text == DONATE_TEXT
    assert "свободное время" in text
    buttons = [(b.text, b.callback_data) for row in markup.inline_keyboard for b in row]
    assert buttons == [
        ("⭐ 50 Stars", "donate:50"),
        ("⭐ 100 Stars", "donate:100"),
        ("⭐ 500 Stars", "donate:500"),
    ]


def test_stars_callback_sends_xtr_invoice(tmp_path):
    bot, dispatcher, _ = make_bot(tmp_path)
    asyncio.run(dispatcher.feed_update(bot, callback_update(bot, 1, "donate:100")))
    assert len(bot.invoices) == 1
    invoice = bot.invoices[0]
    assert invoice.chat_id == 777
    assert invoice.currency == "XTR"
    assert invoice.provider_token == ""
    assert invoice.payload == "donate"
    assert invoice.title
    assert [(price.label, price.amount) for price in invoice.prices] == [("Поддержка", 100)]


def test_every_stars_price_is_offered(tmp_path):
    bot, dispatcher, _ = make_bot(tmp_path)
    for index, stars in enumerate(DONATION_STARS, start=1):
        asyncio.run(
            dispatcher.feed_update(bot, callback_update(bot, index, f"donate:{stars}"))
        )
    assert [invoice.prices[0].amount for invoice in bot.invoices] == list(DONATION_STARS)


def test_unknown_stars_amount_is_rejected(tmp_path):
    bot, dispatcher, _ = make_bot(tmp_path)
    asyncio.run(dispatcher.feed_update(bot, callback_update(bot, 1, "donate:7")))
    assert bot.invoices == []
    assert "Неизвестная сумма" in [a for a in bot.answers if a]
    asyncio.run(dispatcher.feed_update(bot, callback_update(bot, 2, "donate:abc")))
    assert bot.invoices == []


def test_pre_checkout_is_confirmed(tmp_path):
    bot, dispatcher, _ = make_bot(tmp_path)
    asyncio.run(dispatcher.feed_update(bot, pre_checkout_update(bot, 1, amount=100)))
    assert len(bot.checkouts) == 1
    assert bot.checkouts[0].ok is True


def test_successful_payment_is_saved_and_thanked(tmp_path):
    bot, dispatcher, db_path = make_bot(tmp_path)
    asyncio.run(dispatcher.feed_update(bot, paid_update(bot, 1, amount=100)))

    db = DB(db_path)
    rows = db.conn.execute(
        "SELECT user_id, amount, telegram_payment_charge_id FROM donations"
    ).fetchall()
    db.close()
    assert [tuple(row) for row in rows] == [(777, 100, "charge-1")]
    assert bot.sent[-1][1] == DONATION_THANKS


def test_duplicate_charge_is_ignored(tmp_path):
    bot, dispatcher, db_path = make_bot(tmp_path)
    asyncio.run(dispatcher.feed_update(bot, paid_update(bot, 1, charge_id="same")))
    asyncio.run(dispatcher.feed_update(bot, paid_update(bot, 2, charge_id="same")))

    db = DB(db_path)
    count = db.conn.execute("SELECT COUNT(*) FROM donations").fetchone()[0]
    db.close()
    assert count == 1


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


def test_donate_command_sends_support_screen(tmp_path):
    bot, dispatcher, _ = make_bot(tmp_path)
    asyncio.run(dispatcher.feed_update(bot, message_update(bot, 1, "/donate")))
    _, text, markup = bot.sent[-1]
    assert text == DONATE_TEXT
    callbacks = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert callbacks == ["donate:50", "donate:100", "donate:500"]


def build_bot_with_admin(tmp_path, admin_id):
    bot = PaymentBot()
    db_path = str(tmp_path / "t.db")
    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.include_router(build_router(Settings(admin_id=admin_id), db_path))
    return bot, dispatcher, db_path


def test_payment_notifies_admin(tmp_path):
    bot, dispatcher, _ = build_bot_with_admin(tmp_path, admin_id=555)
    asyncio.run(dispatcher.feed_update(bot, paid_update(bot, 1, amount=500)))
    admin_messages = [text for chat_id, text, _ in bot.sent if chat_id == 555]
    assert len(admin_messages) == 1
    assert "🎉" in admin_messages[0]
    assert "Алексей" in admin_messages[0]
    assert "500" in admin_messages[0]
    user_messages = [text for chat_id, text, _ in bot.sent if chat_id == 777]
    assert user_messages[-1] == DONATION_THANKS


def test_no_admin_id_means_no_notification(tmp_path):
    bot, dispatcher, _ = build_bot_with_admin(tmp_path, admin_id=None)
    asyncio.run(dispatcher.feed_update(bot, paid_update(bot, 1, amount=100)))
    assert [chat_id for chat_id, _, _ in bot.sent] == [777]
