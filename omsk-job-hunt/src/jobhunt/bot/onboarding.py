from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from ..config import Settings
from ..db import DB, UserSettings
from ..filters import SPHERES
from .feed import load, send_slice
from .keyboards import (
    SALARY_CHOICES,
    location_keyboard,
    main_menu_keyboard,
    onboarding_start_keyboard,
    salary_keyboard,
    settings_keyboard,
    spheres_keyboard,
    stop_words_keyboard,
)
from .prefs import (
    LOCATIONS,
    STOP_GROUPS,
    parse_custom,
    spheres_label,
    stop_words_label,
    summary,
    toggle_group,
    toggle_sphere,
)

log = logging.getLogger(__name__)

WELCOME = (
    "Привет! Я собираю вакансии Омска и удалёнки без опыта.\n"
    "Настрою выдачу под тебя: четыре вопроса, меньше минуты."
)
LOCATION_PROMPT = "Шаг 1 из 4. Где искать работу?"
SPHERES_PROMPT = (
    "Шаг 2 из 4. Какие сферы тебе интересны? Отмечай кнопки, лишнее снимай повторным нажатием.\n"
    "«Без разницы (все)» — показывать всё, кроме исключённого."
)
STOP_WORDS_PROMPT = (
    "Шаг 3 из 4. Что исключить? Отмечай кнопки, лишнее снимай повторным нажатием.\n"
    "«Другое» — впиши свои слова через запятую."
)
SALARY_PROMPT = "Шаг 4 из 4. Минимальная зарплата?"


class Onboarding(StatesGroup):
    start = State()
    location = State()
    job_types = State()
    stop_words = State()
    salary = State()
    finish = State()


def build_onboarding_router(settings: Settings, db_path: str) -> Router:
    router = Router()

    def prefs_for(user_id: int) -> UserSettings | None:
        db = DB(db_path)
        try:
            return db.get_user_settings(user_id)
        finally:
            db.close()

    async def prefill(state: FSMContext, prefs: UserSettings) -> None:
        await state.update_data(
            city=prefs.city,
            remote=prefs.remote,
            job_types=list(prefs.job_types),
            stop_words=list(prefs.stop_words),
            min_salary=prefs.min_salary,
            awaiting_custom=False,
        )

    async def draft(state: FSMContext) -> dict:
        data = await state.get_data()
        return {
            "city": data.get("city", "Омск"),
            "remote": bool(data.get("remote", False)),
            "job_types": tuple(data.get("job_types", ())),
            "stop_words": tuple(data.get("stop_words", ())),
            "min_salary": int(data.get("min_salary", 40000)),
        }

    async def show_spheres(message: Message, state: FSMContext) -> None:
        data = await draft(state)
        text = SPHERES_PROMPT
        if data["job_types"]:
            text += f"\n\nСейчас выбираю: {spheres_label(data['job_types'])}"
        await message.answer(text, reply_markup=spheres_keyboard(data["job_types"]))

    async def show_stop_words(message: Message, state: FSMContext) -> None:
        data = await draft(state)
        text = STOP_WORDS_PROMPT
        if data["stop_words"]:
            text += f"\n\nСейчас исключаю: {stop_words_label(data['stop_words'])}"
        await message.answer(text, reply_markup=stop_words_keyboard(data["stop_words"]))

    async def finish_onboarding(message: Message, user_id: int, state: FSMContext) -> None:
        await state.set_state(Onboarding.finish)
        data = await draft(state)
        prefs = UserSettings(
            user_id=user_id,
            city=data["city"],
            remote=data["remote"],
            stop_words=data["stop_words"],
            job_types=data["job_types"],
            min_salary=data["min_salary"],
        )
        db = DB(db_path)
        try:
            db.save_user_settings(prefs)
            found = load(db, settings, prefs, "date")
        finally:
            db.close()
        await state.clear()
        await message.answer(
            summary(prefs, has_vacancies=bool(found)),
            reply_markup=main_menu_keyboard(prefs.digest_enabled),
        )
        if found:
            await send_slice(message, settings, db_path, "date", 0, prefs, limit=5)

    @router.message(CommandStart())
    async def start(message: Message, state: FSMContext) -> None:
        await state.clear()
        prefs = prefs_for(message.from_user.id)
        if prefs is None:
            await state.set_state(Onboarding.start)
            await message.answer(WELCOME, reply_markup=onboarding_start_keyboard())
            return
        await message.answer(
            "С возвращением. Выбери сортировку или загляни в ⚙️ Настройки.",
            reply_markup=main_menu_keyboard(prefs.digest_enabled),
        )

    @router.message(Command("cancel"))
    async def cancel(message: Message, state: FSMContext) -> None:
        if await state.get_state() is None:
            await message.answer("Нечего отменять.")
            return
        await state.clear()
        await message.answer("Настройка отменена. /start — начать заново.")

    @router.callback_query(StateFilter(Onboarding.start), F.data == "ob:go")
    async def go(callback: CallbackQuery, state: FSMContext) -> None:
        await callback.answer()
        await prefill(state, UserSettings(user_id=callback.from_user.id))
        await state.set_state(Onboarding.location)
        await callback.message.answer(
            LOCATION_PROMPT, reply_markup=location_keyboard("Омск", False)
        )

    @router.callback_query(StateFilter(Onboarding.location), F.data.startswith("ob:loc:"))
    async def pick_location(callback: CallbackQuery, state: FSMContext) -> None:
        key = callback.data.split(":", 2)[2]
        if key not in LOCATIONS:
            await callback.answer("Неизвестный вариант")
            return
        _, city, remote = LOCATIONS[key]
        await state.update_data(city=city, remote=remote)
        await state.set_state(Onboarding.job_types)
        await callback.answer()
        await show_spheres(callback.message, state)

    @router.callback_query(StateFilter(Onboarding.job_types), F.data == "ob:jt:done")
    async def spheres_done(callback: CallbackQuery, state: FSMContext) -> None:
        await state.set_state(Onboarding.stop_words)
        await callback.answer()
        await show_stop_words(callback.message, state)

    @router.callback_query(StateFilter(Onboarding.job_types), F.data == "ob:jt:any")
    async def spheres_any(callback: CallbackQuery, state: FSMContext) -> None:
        await state.update_data(job_types=[])
        await callback.answer("Без разницы")
        await show_spheres(callback.message, state)

    @router.callback_query(StateFilter(Onboarding.job_types), F.data.startswith("ob:jt:"))
    async def pick_sphere(callback: CallbackQuery, state: FSMContext) -> None:
        key = callback.data.split(":", 2)[2]
        if key not in SPHERES:
            await callback.answer("Неизвестная сфера")
            return
        data = await draft(state)
        await state.update_data(job_types=list(toggle_sphere(data["job_types"], key)))
        await callback.answer()
        await show_spheres(callback.message, state)

    @router.callback_query(StateFilter(Onboarding.stop_words), F.data == "ob:sw:none")
    async def clear_stop_words(callback: CallbackQuery, state: FSMContext) -> None:
        await state.update_data(stop_words=[], awaiting_custom=False)
        await callback.answer("Ничего не исключаю")
        await show_stop_words(callback.message, state)

    @router.callback_query(StateFilter(Onboarding.stop_words), F.data == "ob:sw:custom")
    async def ask_custom(callback: CallbackQuery, state: FSMContext) -> None:
        await state.update_data(awaiting_custom=True)
        await callback.answer()
        await callback.message.answer(
            "Напиши слова через запятую или с новой строки. /cancel — отмена."
        )

    @router.callback_query(StateFilter(Onboarding.stop_words), F.data == "ob:sw:done")
    async def words_done(callback: CallbackQuery, state: FSMContext) -> None:
        await state.set_state(Onboarding.salary)
        await state.update_data(awaiting_custom=False)
        data = await draft(state)
        await callback.answer()
        await callback.message.answer(
            SALARY_PROMPT, reply_markup=salary_keyboard(data["min_salary"])
        )

    @router.callback_query(StateFilter(Onboarding.stop_words), F.data.startswith("ob:sw:"))
    async def toggle_stop_group(callback: CallbackQuery, state: FSMContext) -> None:
        key = callback.data.split(":", 2)[2]
        if key not in STOP_GROUPS:
            await callback.answer("Неизвестная группа")
            return
        data = await draft(state)
        words = toggle_group(data["stop_words"], key)
        await state.update_data(stop_words=list(words), awaiting_custom=False)
        await callback.answer()
        await show_stop_words(callback.message, state)

    @router.message(StateFilter(Onboarding.stop_words), F.text, ~F.text.startswith("/"))
    async def custom_stop_words(message: Message, state: FSMContext) -> None:
        data = await state.get_data()
        if not data.get("awaiting_custom"):
            await message.answer(
                "Жми кнопки ниже или «Другое», чтобы вписать свои слова.",
                reply_markup=stop_words_keyboard(tuple(data.get("stop_words", ()))),
            )
            return
        added = parse_custom(message.text)
        if not added:
            await message.answer("Не разобрал ни одного слова. Попробуй ещё раз или нажми «Готово».")
            return
        merged = tuple(
            dict.fromkeys(tuple(data.get("stop_words", ())) + added)
        )
        await state.update_data(stop_words=list(merged), awaiting_custom=False)
        await message.answer(f"Добавил: {', '.join(added)}")
        await show_stop_words(message, state)

    @router.callback_query(StateFilter(Onboarding.salary), F.data.startswith("ob:sal:"))
    async def pick_salary(callback: CallbackQuery, state: FSMContext) -> None:
        try:
            value = int(callback.data.split(":", 2)[2])
        except ValueError:
            await callback.answer("Сломалась кнопка")
            return
        if value not in SALARY_CHOICES:
            await callback.answer("Неизвестная сумма")
            return
        await state.update_data(min_salary=value)
        await callback.answer()
        await finish_onboarding(callback.message, callback.from_user.id, state)

    @router.callback_query(F.data == "settings")
    async def open_settings(callback: CallbackQuery, state: FSMContext) -> None:
        prefs = prefs_for(callback.from_user.id)
        await callback.answer()
        if prefs is None:
            await state.set_state(Onboarding.start)
            await callback.message.answer(WELCOME, reply_markup=onboarding_start_keyboard())
            return
        await prefill(state, prefs)
        await state.set_state(Onboarding.location)
        await callback.message.answer(
            "Настройки. Шаг 1 из 4. Где искать? Текущий выбор отмечен галочкой.",
            reply_markup=settings_keyboard(prefs.city, prefs.remote),
        )

    @router.callback_query(F.data == "settings:reset")
    async def reset_settings(callback: CallbackQuery, state: FSMContext) -> None:
        db = DB(db_path)
        try:
            db.delete_user_settings(callback.from_user.id)
        finally:
            db.close()
        await state.clear()
        await state.set_state(Onboarding.start)
        await callback.answer("Настройки сброшены")
        await callback.message.answer(
            "Настройки сброшены. Настроим заново.\n\n" + WELCOME,
            reply_markup=onboarding_start_keyboard(),
        )

    @router.callback_query(F.data.startswith("ob:"))
    async def stale_step(callback: CallbackQuery) -> None:
        await callback.answer(
            "Эта кнопка устарела. Нажми /start и настрой заново.", show_alert=True
        )

    return router
