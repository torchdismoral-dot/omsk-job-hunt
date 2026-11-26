from jobhunt.bot.keyboards import (
    empty_state_keyboard,
    location_keyboard,
    main_menu_keyboard,
    salary_keyboard,
    settings_keyboard,
    spheres_keyboard,
    stop_words_keyboard,
)
from jobhunt.bot.prefs import (
    STOP_GROUPS,
    location_key,
    parse_custom,
    spheres_label,
    stop_words_label,
    summary,
    toggle_group,
    toggle_sphere,
)
from jobhunt.db import UserSettings

CONSTRUCTION = STOP_GROUPS["construction"][1]
SALES = STOP_GROUPS["sales"][1]


def callbacks(keyboard):
    return [button.callback_data for row in keyboard.inline_keyboard for button in row]


def labels(keyboard):
    return [button.text for row in keyboard.inline_keyboard for button in row]


def test_stop_groups_cover_required_choices():
    assert STOP_GROUPS["construction"][0] == "Стройка/Рабочие"
    assert STOP_GROUPS["sales"][0] == "Продажи/Холодные звонки"
    assert STOP_GROUPS["callcenter"][0] == "Колл-центр"


def test_parse_custom_splits_and_normalizes():
    assert parse_custom("Курьер,  Вахта; сварщик\nповар") == ("курьер", "вахта", "сварщик", "повар")


def test_parse_custom_dedupes_and_ignores_empty():
    assert parse_custom(",, курьер ,, курьер, ") == ("курьер",)
    assert parse_custom("   ") == ()


def test_toggle_group_adds_and_removes():
    words = toggle_group((), "sales")
    assert words == SALES
    assert toggle_group(words, "sales") == ()


def test_toggle_group_keeps_custom_words():
    words = toggle_group(("курьер",), "construction")
    assert "курьер" in words
    assert set(CONSTRUCTION) <= set(words)


def test_location_key_mapping():
    assert location_key("Омск", False) == "omsk"
    assert location_key(None, True) == "remote"
    assert location_key("Омск", True) == "all"


def test_summary_new_user():
    prefs = UserSettings(user_id=1, city="Омск", remote=False, min_salary=40000)
    text = summary(prefs)
    assert text == (
        "Настройки сохранены! Ищу: Омск, сферы: все, ЗП от 40 000 ₽, "
        "исключаю: ничего. Вот первые 5 вакансий:"
    )


def test_summary_all_location_with_groups_and_custom():
    prefs = UserSettings(
        user_id=1,
        city="Омск",
        remote=True,
        stop_words=SALES + ("курьер",),
        job_types=("it", "banking"),
        min_salary=55000,
    )
    text = summary(prefs)
    assert "Ищу: Омск и удалёнка" in text
    assert "сферы: 💼 Банки и финансы, 💻 IT и интернет" in text
    assert "ЗП от 55 000 ₽" in text
    assert "исключаю: Продажи/Холодные звонки, «курьер»" in text


def test_stop_words_label_empty():
    assert stop_words_label(()) == "ничего"


def test_main_menu_has_settings_button():
    keyboard = main_menu_keyboard()
    assert callbacks(keyboard)[:3] == ["top:date", "top:salary", "top:distance"]
    assert "settings" in callbacks(keyboard)
    assert any("Настройки" in text for text in labels(keyboard))


def test_location_keyboard_marks_current_choice():
    keyboard = location_keyboard("Омск", False)
    texts = labels(keyboard)
    assert texts[0].startswith("✅ Омск")
    assert not texts[1].startswith("✅")
    assert callbacks(keyboard) == ["ob:loc:omsk", "ob:loc:remote", "ob:loc:all"]


def test_stop_words_keyboard_has_groups_other_none_done():
    keyboard = stop_words_keyboard(SALES)
    data = callbacks(keyboard)
    assert "ob:sw:construction" in data
    assert "ob:sw:sales" in data
    assert "ob:sw:callcenter" in data
    assert "ob:sw:custom" in data
    assert "ob:sw:none" in data
    assert "ob:sw:done" in data
    sales_button = next(
        button
        for row in keyboard.inline_keyboard
        for button in row
        if button.callback_data == "ob:sw:sales"
    )
    assert sales_button.text.startswith("✅")
    assert any("Другое" in text for text in labels(keyboard))
    assert any("Ничего не исключать" in text for text in labels(keyboard))


def test_salary_keyboard_values():
    keyboard = salary_keyboard(55000)
    assert callbacks(keyboard) == [
        "ob:sal:30000", "ob:sal:40000", "ob:sal:55000", "ob:sal:80000",
    ]
    assert labels(keyboard)[2].startswith("✅ 55")


def test_settings_keyboard_has_locations_and_reset():
    keyboard = settings_keyboard("Омск", False)
    assert callbacks(keyboard) == [
        "ob:loc:omsk", "ob:loc:remote", "ob:loc:all", "settings:reset",
    ]
    assert labels(keyboard)[-1] == "🔄 Сбросить всё"


def test_empty_state_keyboard_leads_to_settings():
    keyboard = empty_state_keyboard()
    assert callbacks(keyboard) == ["settings"]
    assert labels(keyboard) == ["⚙️ Настройки"]


def test_spheres_keyboard_has_seven_spheres_any_and_done():
    keyboard = spheres_keyboard(())
    assert callbacks(keyboard) == [
        "ob:jt:banking", "ob:jt:it", "ob:jt:support", "ob:jt:admin",
        "ob:jt:sales", "ob:jt:logistics", "ob:jt:blue_collar",
        "ob:jt:any", "ob:jt:done",
    ]
    assert labels(keyboard)[0] == "⬜ 💼 Банки и финансы"
    assert "✅ 🌐 Без разницы (все)" in labels(keyboard)
    assert labels(keyboard)[-1] == "Готово"


def test_spheres_keyboard_marks_selected_and_unmarks_any():
    keyboard = spheres_keyboard(("it",))
    texts = labels(keyboard)
    assert "✅ 💻 IT и интернет" in texts
    assert "⬜ 💼 Банки и финансы" in texts
    assert "⬜ 🌐 Без разницы (все)" in texts


def test_toggle_sphere_adds_removes_and_keeps_order():
    assert toggle_sphere((), "it") == ("it",)
    assert toggle_sphere(("it",), "it") == ()
    assert toggle_sphere(("logistics",), "it") == ("it", "logistics")
    assert toggle_sphere(("unknown",), "it") == ("it",)


def test_toggle_sphere_any_clears_selection():
    assert toggle_sphere(("it", "banking"), "any") == ()


def test_spheres_label_empty_means_all():
    assert spheres_label(()) == "все"
    assert spheres_label(("it", "banking")) == "💼 Банки и финансы, 💻 IT и интернет"
