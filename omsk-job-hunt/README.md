# OmWork — карьера в Омске

Telegram-бот поиска вакансий: SuperJob + «Работа России» + hh.ru, фильтры под новичка
без опыта, сферы, стоп-слова, личный порог зарплаты, дайджест и донаты через Telegram Stars.

## Локальный запуск

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env          # вписать BOT_TOKEN и SUPERJOB_KEY
PYTHONPATH=src python -m jobhunt.bot.app
```

Проверки и обслуживание:

```bash
PYTHONPATH=src python -m pytest -q
PYTHONPATH=src python -m jobhunt.cli refresh    # собрать вакансии
PYTHONPATH=src python -m jobhunt.cli top --by salary
PYTHONPATH=src python -m jobhunt.cli stats
```

## Деплой на Amvera

1. Залей репозиторий на GitHub и подключи его в панели Amvera
   (или загрузи архив через вкладку «Файлы»).
2. Во вкладке **«Переменные окружения»** задай:

   | Переменная     | Значение                                   |
   |----------------|--------------------------------------------|
   | `BOT_TOKEN`    | токен от @BotFather                        |
   | `SUPERJOB_KEY` | ключ приложения SuperJob                   |
   | `ADMIN_ID`     | твой telegram user_id для уведомлений о донатах (необязательно) |

   `ADMIN_ID` из панели важнее значения в `config.yaml` — одноимённая переменная
   окружения перекрывает файл.

3. Включи **постоянный диск** (persistence) и примонтируй его в `/data`, затем добавь:

   | Переменная        | Значение            |
   |-------------------|---------------------|
   | `JOBHUNT_DB`      | `/data/jobhunt.db`  |
   | `JOBHUNT_FSM_DB`  | `/data/fsm.db`      |

   Без тома база вакансий и онбординг-состояния обнуляются при каждом деплое.

4. Сборка идёт по `requirements.txt`, запуск — по `amvera.yml`: `python main.py`.

### Как деплоить

Git-репозиторий лежит выше проекта (в `D:\CLAUDE CODE`), а Amvera требует
`amvera.yml` в корне репозитория. Поэтому деплой идёт из **`omwork/`** — это
отдельный репозиторий с тем же кодом, а корень остаётся источником правды:

```bash
.\scripts\sync_omwork.ps1 -Push -Message "Добавить коллектор hh.ru"
```

Скрипт зеркалит `src/`, `tests/`, `scripts/` и файлы конфигурации в `omwork/`
(секреты `.env` и локальные базы не трогает), затем коммитит и делает
`git push -f amvera master`. `omwork/` добавлен в `.gitignore` корня, чтобы
копия не попадала в основной репозиторий.

Проверить сбор после деплоя: отправить боту `/refresh` — он вернёт счётчики
`Собрано с hh.ru: N`, а при блокировке hh — строку `⚠️ hh: ...`.

`.env` на хостинг не нужен и не должен туда попадать — он в `.gitignore`.

## Переменные окружения

| Переменная        | По умолчанию  | Назначение                                  |
|-------------------|---------------|---------------------------------------------|
| `BOT_TOKEN`       | —             | токен бота, обязателен                      |
| `SUPERJOB_KEY`    | —             | ключ SuperJob API                           |
| `ADMIN_ID`        | —             | user_id для уведомлений о донатах           |
| `JOBHUNT_DB`      | `jobhunt.db`  | путь к базе вакансий                        |
| `JOBHUNT_FSM_DB`  | `fsm.db`      | путь к хранилищу состояний онбординга       |
| `JOBHUNT_CONFIG`  | `config.yaml` | путь к конфигу                              |
| `JOBHUNT_LOG_FILE`| `bot.log`     | файл лога; пустое значение — только stdout  |
| `HH_PROXY`        | —             | резидентный прокси для hh.ru: `http://user:pass@host:port` (не обязателен) |

Логи по умолчанию идут в **stdout** (их забирает платформа) и дублируются в `bot.log`,
если файл удаётся открыть.

## Источники вакансий

| Источник | Как берём | Настройка |
|---|---|---|
| SuperJob | официальный API, ключ `SUPERJOB_KEY` | `superjob:` в `config.yaml` |
| hh.ru | страница выдачи, JSON в `HH-Lux-InitialState` (API закрыт) | `hh:` в `config.yaml` |
| trudvsem | открытые данные без ключа | `trudvsem:` в `config.yaml` |

hh отключается одной строкой `hh: {enabled: false}` — сбор остальных площадок
продолжается. Фикстуру выдачи обновлять вручную: `python scripts/fetch_hh_fixture.py`.

## Docker (альтернатива)

```bash
docker build -t omwork .
docker run -d --env-file .env -v omwork_data:/data omwork
```

Контейнер слушает не порт, а Telegram long polling, поэтому порты публиковать не нужно.
Данные монтируются в `/data`.

## Структура

```
src/jobhunt/        сбор, фильтры, рендер, CLI
src/jobhunt/bot/    aiogram-бот, онбординг, дайджест, донаты
tests/              pytest
config.yaml         порог зарплаты, стоп-слова, сферы, time-настройки
```
