# OMSK JOB HUNT — ТЗ v3

Версия от 26.11.2026. Заменяет v2: тот был построен на hh API, который закрыт для соискателей.

---

## 0. Состояние источников

| Источник | Статус | Почему |
|---|---|---|
| hh.ru API | **вычеркнут** | поддержка для соискателей прекращена 15.12.2025; `/vacancies` отдаёт 403 при любом UA, в браузере и без VPN |
| SuperJob API | **рабочий, основной** | ключ приложения `OmWork` (ID 5377) проверен 26.11.2026 |
| trudvsem (Работа России) | рабочий, второй | открытый JSON без ключа, но видно ~2% базы |

---

## 1. Цель v1

Telegram-бот, который раз в 2 дня собирает вакансии по Омску и удалёнке, фильтрует «без опыта / джун», ранжирует и присылает то, **чего ещё не присылал**.

Один пользователь (владелец). Монетизация — вне v1.

**Не делаем в v1:** Playwright, скрейпинг сайтов, банков, веб-интерфейс, оплата, мультипрофили.

---

## 2. SuperJob — основной источник

Ключ приложения лежит в `.env` строкой `SUPERJOB_KEY=...` (в git не попадает, есть в `.gitignore`).

```
GET https://api.superjob.ru/2.0/vacancies/
Header: X-Api-App-Id: <SUPERJOB_KEY>
```

### 2.1 Замеры на живом API (26.11.2026)

| Запрос | Всего вакансий |
|---|---|
| `town=17` (Омск), все | 668 |
| `town=17&period=2` | 487 |
| `town=17&period=7` | 665 |
| `town=17&place_of_work=2` (удалёнка в Омске) | 13 |
| `place_of_work=2` (удалёнка по РФ) | 1358 |

Омск — `town=17`. `[ИСПРАВЛЕНО]` В hh это был `area=68`, у SuperJob нумерация своя: **68 = не Омск**.
Омская область — `region=52`.

### 2.2 Ловушки API

- **Страница не больше 40 записей.** `count=50` и `count=100` возвращают те же 40. Значит пагинация по 40.
- **`experience` НЕ фильтруется на сервере.** Параметр молча игнорируется: `experience=0` не меняет `total`. Фильтр только на клиенте по полю `experience.id`.
- **`payment_from=40000` не отсекает беззарплатные вакансии** (665 из 668 проходят). Порог тоже проверяем на клиенте.
- `payment_from = 0` и `payment_to = 0` означают «не указано», а не ноль.
- Валюта — `"rub"` в нижнем регистре.
- `date_published` — unix-время в секундах.
- `address` — строка («Пенза»), не объект. Район города в ней обычно отсутствует.
- Флага gross/net в ответе нет. Зарплату берём как есть, без пересчёта, и помечаем как «неизвестно, до или после НДФЛ».

### 2.3 Значения справочников

`experience.id`: `0` — Не имеет значения, `1` — **Без опыта**, `2` — От 1 года, `3` — От 3 лет.
`place_of_work.id`: `0` — не указано, `1` — на территории работодателя, `2` — **удалённая работа**, `3` — разъездная.

### 2.4 Запросы прогона

**Офис (Омск):**
```
town=17
period=2
count=40
page=0..N-1
order_field=date
order_direction=desc
```
За 2 дня по Омску — ~487 вакансий, это ~13 страниц по 40.

**Удалёнка (вся РФ):**
```
place_of_work=2
period=2
count=40
page=0..N-1
keyword=<ключевые слова>
```
Удалёнка по РФ без ключевых слов даёт слишком широкую выборку (1358 за всё время) — прогоняем по списку слов из config.

### 2.5 Поля ответа, которые используем

```
id, profession, firm_name, firm_activity, link,
town.id, town.title, address, latitude, longitude,
payment_from, payment_to, currency,
experience.id, experience.title,
place_of_work.id, place_of_work.title, type_of_work.title,
date_published, work, candidat, compensation, catalogues
```

---

## 3. trudvsem — второй источник

```
GET https://opendata.trudvsem.ru/api/v1/vacancies/region/5500000000000
```

- Без ключа, без авторизации.
- `offset` упирается в ~150–199: дальше сервер отвечает 500. `page` игнорируется. Видно ~2% базы.
- Пул — рабочие специальности, образование, медицина. IT и офис почти нет.
- Роль: добить дайджест «свежаком», который SuperJob не покрывает.

Поля: `vacancy.id`, `vacancy.job-name`, `vacancy.company.name`, `vacancy.region.name`, `vacancy.salary_min`, `vacancy.salary_max`, `vacancy.requirement.experience`, `vacancy.creation-date`, `vacancy.vac_url`, `vacancy.addresses.address[0].location`.

`[ИСПРАВЛЕНО]` Проверено на фикстуре 26.11.2026: `salary` — строка вида «от 46500», а числа лежат отдельно в `salary_min` / `salary_max`. Дата — `creation-date`, не `publication-date`. Адрес — `addresses.address[0].location`, полная строка («Омская область, г Омск, Бульварная улица, дом 7»), района города в ней нет.

`[ДОПУЩЕНИЕ]` `requirement.experience` приходит целым числом (в фикстуре встречаются 0, 1, 6), а не строкой. Трактуем как требуемый стаж в годах: 0 → «Без опыта», 1 → «От 1 года», N → «От N лет». Проверить на живых данных и поправить, если окажется кодовым значением.

---

## 4. Нормализация

Обе площадки приводятся к одной записи:

| Поле | SuperJob | trudvsem |
|---|---|---|
| `source` | `superjob` | `trudvsem` |
| `source_id` | `id` (int) | `vacancy.id` |
| `title` | `profession` | `job-name` |
| `company` | `firm_name` | `company.name` |
| `salary_from` | `payment_from or None` | `salary_min or None` |
| `salary_to` | `payment_to or None` | `salary_max or None` |
| `currency` | `currency` (`rub`) | `RUB` |
| `city` | `town.title` | из `addresses[0].location` |
| `is_remote` | `place_of_work.id == 2` | по тексту `schedule` |
| `experience` | `experience.title` | `requirement.experience` |
| `url` | `link` | `vac_url` |
| `published_at` | `date_published` (unix → ISO) | `creation-date` |

Ключ вакансии в БД: `source || ':' || source_id` — id у площадок пересекаются.

---

## 5. Хранилище

SQLite, `aiosqlite`. Без хранилища дайджест повторяет одно и то же.

```sql
CREATE TABLE vacancies (
  key             TEXT PRIMARY KEY,      -- 'superjob:48374898'
  source          TEXT NOT NULL,
  source_id       TEXT NOT NULL,
  title           TEXT NOT NULL,
  company         TEXT,
  salary_from     INTEGER,               -- NULL = не указана
  salary_to       INTEGER,
  currency        TEXT,
  city            TEXT,
  district        TEXT,                  -- Кировский / Центральный / NULL
  is_remote       INTEGER NOT NULL DEFAULT 0,
  experience      TEXT,
  url             TEXT NOT NULL,
  published_at    TEXT,
  first_seen_at   TEXT NOT NULL,
  last_seen_at    TEXT NOT NULL,
  red_flags       TEXT,                  -- JSON array
  raw             TEXT
);

CREATE TABLE sent (
  vacancy_key TEXT NOT NULL,
  chat_id     INTEGER NOT NULL,
  kind        TEXT NOT NULL,             -- 'digest' | 'top'
  sent_at     TEXT NOT NULL,
  PRIMARY KEY (vacancy_key, chat_id, kind)
);

CREATE TABLE subscriptions (
  chat_id    INTEGER PRIMARY KEY,
  created_at TEXT NOT NULL,
  active     INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at TEXT, finished_at TEXT,
  fetched INTEGER, fresh INTEGER, error TEXT
);
```

Новизна: ключа нет в `vacancies` → вакансия новая → попадает в дайджест.

---

## 6. Фильтр

Порядок — от дешёвого к дорогому.

1. **География.** `city == 'Омск'` ИЛИ `is_remote`. Иначе отбрасываем.
2. **Опыт.** Оставляем `Без опыта`, `Не имеет значения`, `От 1 года` (на джуна смотрят и такие). `От 3 лет` — отбрасываем. Список настраивается в config.
3. **Стоп-слова** (config) по `title + company + description`: попадание → `red_flags`, **не выбрасываем**.
   `продаж`, `холодные звонки`, `колл-центр`, `call-центр`, `взыскан`, `телемаркетинг`, `без оплаты`, `оплата по результату`.
3a. **Жёсткий стоп-лист** (`drop_words`, config) — такие вакансии выбрасываются совсем: `военнослужащ`, `по контракту`, `беспилотн`, `вахт`.
   `[ДОБАВЛЕНО]` Иначе топ по ЗП занимают армейские контракты от 3 млн ₽ и вахтовые вакансии из других регионов.
4. **Зарплата.** Порог **40 000 ₽**.
   - `salary_from >= 40000` → проходит
   - `salary_from` пусто и `salary_to >= 40000` → проходит
   - оба пусты → `salary_unknown`, **оставляем** (идут в топ с пометкой)
   - иначе → отбрасываем
5. **Исключения работодателей** по названию компании (config, пусто по умолчанию).

---

## 7. Ранжирование

| Режим | Сортировка |
|---|---|
| По дате | `published_at` desc |
| По ЗП | `salary_from` desc, пустые **в конец** |
| По близости | см. ниже |

**По близости** — по координатам, а не по тексту.

1. Если у вакансии есть `lat`/`lng` и в config задан `home.lat`/`home.lng` — считаем расстояние по haversine, ближние первыми.
2. Нет координат, но в тексте адреса/названия есть округ: «Кировский» → раньше, «Центральный» → следом.
3. Остальной Омск.
4. Удалёнка — всегда в конце, даже если координаты близко.

`[ИСПРАВЛЕНО]` Раньше близость определялась только по тексту округа. На живой выгрузке округ не нашёлся ни у одной из 689 вакансий (`address` у SuperJob — просто «Омск»), режим вырождался в сортировку по дате. Координаты есть у части вакансий SuperJob и у trudvsem (`addresses[0].lat/lng`), поэтому сортировка теперь по ним. `home` по умолчанию — центр Омска; владелец меняет под себя.

---

## 8. Бот (aiogram 3)

- Токен: `BOT_TOKEN` из окружения, `.env` не коммитить.
- `/start` — краткая подсказка.
- `/top` — inline-кнопки «По дате» / «По ЗП» / «По близости». Топ-10 одним сообщением:
  ```
  1. Монтажник строительных лесов — КХМ Арктик
     180 000 ₽ · Омск · 25.11
     https://omsk.superjob.ru/vakansii/...
  ```
- `/subscribe` — включает подписку, `/unsubscribe` — выключает.
- 4096 символов на сообщение — режем по 8 вакансий.
- «Показать ещё» — следующие 10.

---

## 9. Планировщик

`APScheduler` (`AsyncIOScheduler`) в том же loop, что aiogram.

- Интервал 48 часов, первый запуск при старте.
- Дайджест = вакансии, которых нет в `sent` для этого `chat_id`.
- Новых нет — **молчим**.
- После успешной отправки пишем в `sent`.

---

## 10. Схема проекта

```
omsk-job-hunt/
├── SPEC.md
├── config.yaml
├── .env            # SUPERJOB_KEY, BOT_TOKEN — не коммитить
├── .env.example
├── requirements.txt
├── src/jobhunt/
│   ├── __init__.py
│   ├── config.py            # yaml + env, валидация
│   ├── db.py                # schema, upsert, mark_sent, get_unsent
│   ├── superjob.py          # клиент API, пагинация по 40, паузы
│   ├── trudvsem.py          # клиент открытых данных
│   ├── normalize.py         # raw JSON -> запись, единая схема
│   ├── filters.py           # география, опыт, стоп-слова, зарплата
│   ├── render.py            # общий текст: деньги, дата, место, расстояние
│   ├── ranker.py            # by_date / by_salary / by_distance
│   ├── pipeline.py          # fetch -> normalize -> filter -> upsert -> rank
│   ├── cli.py               # python -m jobhunt.cli top --by salary
│   └── bot/
│       ├── app.py           # Bot, Dispatcher, polling
│       ├── handlers.py      # /start, /top, callback top:/more:
│       ├── keyboards.py     # три режима + «показать ещё»
│       └── messages.py      # HTML-рендер, по 8 вакансий на сообщение
└── tests/
    ├── fixtures/superjob_omsk.json
    ├── fixtures/trudvsem_omsk.json
    ├── test_normalize.py
    ├── test_filters.py
    └── test_ranker.py
```

`requirements.txt` для M1: `pyyaml` + `pytest`. HTTP и SQLite — на стандартной библиотеке (`urllib`, `sqlite3`), чтобы не зависеть от колёс под Python 3.15. Асинхронный стек (`aiogram`, `apscheduler`) добавляется в M2–M3.

---

## 11. config.yaml

```yaml
superjob:
  base_url: "https://api.superjob.ru/2.0"
  key_env: SUPERJOB_KEY
  page_size: 40
  delay_ms: 300

trudvsem:
  base_url: "https://opendata.trudvsem.ru/api/v1"
  region: "5500000000000"
  max_records: 150

search:
  town_omsk: 17
  remote_keywords: [помощник, оператор, младший, стажёр, junior, поддержка]

filter:
  salary_min: 40000
  keep_unknown_salary: true
  allowed_experience: [Без опыта, Не имеет значения, От 1 года]
  stop_words: [продаж, холодные звонки, колл-центр, call-центр, взыскан, телемаркетинг, без оплаты, оплата по результату]
  exclude_companies: []

rank:
  home_districts: [Кировский, Центральный]
  top_n: 10

bot:
  token_env: BOT_TOKEN
  digest_hours: 48
```

---

## 12. Тесты

Фикстуры — реальные ответы API, сохранённые в файлы. Тесты работают **без сети**.

Обязательно покрыть:
- `payment_to = 0` читается как «не указана», а не как ноль;
- вакансия только с `payment_from`, только с `payment_to`, без зарплаты;
- без зарплаты → `salary_unknown`, не выброшена;
- `experience.id == 3` («От 3 лет») отброшена, `1` и `2` — остались;
- стоп-слово → `red_flags` содержит его, вакансия осталась;
- удалёнка из другого города прошла, офис из Новосибирска — нет;
- `by_salary` ставит пустые в конец;
- повторный прогон не отдаёт уже отправленное;
- ключи `superjob:123` и `trudvsem:123` не конфликтуют.

---

## 13. Этапы

| Этап | Результат | Условие перехода |
|---|---|---|
| M0 | ключ SuperJob проверен | `/vacancies/` отдаёт JSON — **закрыт 26.11.2026** |
| M1 | `python -m jobhunt.cli top` печатает 10 вакансий | 80 тестов зелёные, живой прогон 556 вакансий — **закрыт 26.11.2026** |
| M2 | бот: `/top` с кнопками | роутер и сообщения покрыты тестами; живой запуск 26.11.2026 — **закрыт** |
| M3 | подписка + дайджест + дедуп | `sent` не даёт повторно отправить; без новинок молчит — **написан 26.11.2026**, 104 теста |
| M4 | «по близости» по координатам | ближние первыми, удалёнка в конце — **закрыт вместе с M1** |

---

## 14. Риски

| Риск | Что делаем |
|---|---|
| SuperJob режет бесплатный тариф по лимиту запросов | один прогон в 2 дня, паузы 300 мс, логировать 429 |
| `count` больше 40 молча обрезается | пагинация строго по 40, условие остановки — `more == false` |
| Малый объём «без опыта» по Омску | добираем «От 1 года» и trudvsem |
| Компьютер спит | первый релиз на ПК; деплой позже |
| Python 3.15 слишком новый, колёса aiogram/pydantic могут не поставиться | проверить `pip install` на M1; при проблемах — venv на 3.12 |
| Зарплата неизвестно до/после НДФЛ | не пересчитываем, помечаем как есть |
