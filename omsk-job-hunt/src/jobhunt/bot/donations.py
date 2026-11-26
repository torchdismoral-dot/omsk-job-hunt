from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, LabeledPrice, Message, PreCheckoutQuery

from ..config import Settings
from ..db import DB
from .keyboards import DONATION_STARS, donate_keyboard
from .messages import DONATE_TEXT, DONATION_THANKS

log = logging.getLogger(__name__)

INVOICE_TITLE = "Поддержка проекта OmWork"
DONATE_PAYLOAD = "donate"


def donor_name(message: Message) -> str:
    user = message.from_user
    if user.username:
        return f"@{user.username}"
    return user.full_name or str(user.id)


def build_donate_router(settings: Settings, db_path: str) -> Router:
    router = Router()

    @router.message(Command("donate"))
    async def donate_command(message: Message) -> None:
        await message.answer(DONATE_TEXT, reply_markup=donate_keyboard())

    @router.callback_query(F.data == "donate")
    async def show_donate(callback: CallbackQuery) -> None:
        await callback.answer()
        await callback.message.answer(DONATE_TEXT, reply_markup=donate_keyboard())

    @router.callback_query(F.data.startswith("donate:"))
    async def send_stars_invoice(callback: CallbackQuery) -> None:
        try:
            stars = int(callback.data.split(":", 1)[1])
        except ValueError:
            stars = 0
        if stars not in DONATION_STARS:
            await callback.answer("Неизвестная сумма")
            return
        await callback.answer()
        # Telegram Stars: currency XTR, provider_token не нужен
        await callback.bot.send_invoice(
            chat_id=callback.from_user.id,
            title=INVOICE_TITLE,
            description=f"Поддержка бота на {stars} ⭐",
            payload=DONATE_PAYLOAD,
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(label="Поддержка", amount=stars)],
        )

    @router.pre_checkout_query()
    async def confirm_checkout(query: PreCheckoutQuery) -> None:
        await query.answer(ok=True)

    @router.message(F.successful_payment)
    async def payment_received(message: Message) -> None:
        payment = message.successful_payment
        db = DB(db_path)
        try:
            fresh = db.add_donation(
                message.from_user.id,
                payment.total_amount,
                payment.telegram_payment_charge_id,
            )
        finally:
            db.close()
        if not fresh:
            log.info("Повтор successful_payment %s пропущен", payment.telegram_payment_charge_id)
        if settings.admin_id:
            try:
                await message.bot.send_message(
                    settings.admin_id,
                    f"🎉 Пользователь {donor_name(message)} поддержал проект "
                    f"на {payment.total_amount} Stars!",
                )
            except Exception:  # админ мог не начинать чат с ботом
                log.exception("Не удалось уведомить админа о донате")
        await message.answer(DONATION_THANKS)

    return router
