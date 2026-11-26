from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_STOP_WORDS = (
    "продаж",
    "холодные звонки",
    "колл-центр",
    "call-центр",
    "взыскан",
    "телемаркетинг",
    "без оплаты",
    "оплата по результату",
)
DEFAULT_ALLOWED_EXPERIENCE = ("Без опыта", "Не имеет значения", "От 1 года")

DEFAULT_DROP_WORDS = ("военнослужащ", "по контракту", "беспилотн", "вахт")

# Отсев по названию вакансии: медицина, образование, торговый зал, заграничные стройки.
# Рабочие специальности и курьеры сюда больше не входят: их отбирают сферы пользователя.
DEFAULT_TITLE_DROP_WORDS = (
    "уборщик",
    "повар",
    "пекар",
    "продавец",
    "охранник",
    "дворник",
    "учител",
    "преподавател",
    "педагог",
    "воспитател",
    "репетитор",
    "врач",
    "медицин",
    "фельдшер",
    "медсестр",
    "поликлиник",
    "стоматолог",
    "фармацевт",
    "санитар",
    "египет",
    "сирия",
    "африка",
    "китай",
)


def load_dotenv(path: str | Path = ".env") -> None:
    """Мини-замена python-dotenv: только KEY=VALUE, окружение не перезаписывает."""
    file = Path(path)
    if not file.exists():
        return
    for line in file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass
class FilterConfig:
    salary_min: int = 40000
    keep_unknown_salary: bool = True
    allowed_experience: tuple[str, ...] = DEFAULT_ALLOWED_EXPERIENCE
    stop_words: tuple[str, ...] = DEFAULT_STOP_WORDS
    drop_words: tuple[str, ...] = DEFAULT_DROP_WORDS
    title_drop_words: tuple[str, ...] = DEFAULT_TITLE_DROP_WORDS
    exclude_companies: tuple[str, ...] = ()
    max_distance_km: float = 150.0


@dataclass
class SourcesConfig:
    superjob_base_url: str = "https://api.superjob.ru/2.0"
    superjob_key_env: str = "SUPERJOB_KEY"
    page_size: int = 40
    delay_ms: int = 300
    max_pages: int = 20
    trudvsem_base_url: str = "https://opendata.trudvsem.ru/api/v1"
    trudvsem_region: str = "5500000000000"
    trudvsem_limit: int = 150


@dataclass
class Settings:
    town_omsk: int = 17
    remote_keywords: tuple[str, ...] = ()
    top_n: int = 10
    digest_hours: int = 48
    refresh_hour: int = 9
    admin_id: int | None = None
    home_lat: float | None = None
    home_lng: float | None = None
    sources: SourcesConfig = field(default_factory=SourcesConfig)
    filters: FilterConfig = field(default_factory=FilterConfig)

    @property
    def home(self) -> tuple[float, float] | None:
        if self.home_lat is None or self.home_lng is None:
            return None
        return (self.home_lat, self.home_lng)

    @property
    def superjob_key(self) -> str | None:
        return os.environ.get(self.sources.superjob_key_env)


def load_config(path: str | Path = "config.yaml") -> Settings:
    file = Path(path)
    data = yaml.safe_load(file.read_text(encoding="utf-8")) if file.exists() else None
    data = data or {}
    settings = Settings()

    sources = data.get("superjob") or {}
    settings.sources.superjob_base_url = sources.get("base_url", settings.sources.superjob_base_url)
    settings.sources.superjob_key_env = sources.get("key_env", settings.sources.superjob_key_env)
    settings.sources.page_size = int(sources.get("page_size", settings.sources.page_size))
    settings.sources.delay_ms = int(sources.get("delay_ms", settings.sources.delay_ms))

    trud = data.get("trudvsem") or {}
    settings.sources.trudvsem_base_url = trud.get("base_url", settings.sources.trudvsem_base_url)
    settings.sources.trudvsem_region = str(trud.get("region", settings.sources.trudvsem_region))
    settings.sources.trudvsem_limit = int(trud.get("max_records", settings.sources.trudvsem_limit))

    search = data.get("search") or {}
    settings.town_omsk = int(search.get("town_omsk", settings.town_omsk))
    settings.remote_keywords = tuple(search.get("remote_keywords") or ())

    filt = data.get("filter") or {}
    settings.filters.salary_min = int(filt.get("salary_min", settings.filters.salary_min))
    settings.filters.keep_unknown_salary = bool(
        filt.get("keep_unknown_salary", settings.filters.keep_unknown_salary)
    )
    if filt.get("allowed_experience"):
        settings.filters.allowed_experience = tuple(filt["allowed_experience"])
    if filt.get("stop_words"):
        settings.filters.stop_words = tuple(filt["stop_words"])
    if "drop_words" in filt:
        settings.filters.drop_words = tuple(filt["drop_words"] or ())
    if "title_drop_words" in filt:
        settings.filters.title_drop_words = tuple(filt["title_drop_words"] or ())
    settings.filters.max_distance_km = float(
        filt.get("max_distance_km", settings.filters.max_distance_km)
    )
    settings.filters.exclude_companies = tuple(filt.get("exclude_companies") or ())

    home = data.get("home") or {}
    if home.get("lat") is not None and home.get("lng") is not None:
        settings.home_lat = float(home["lat"])
        settings.home_lng = float(home["lng"])

    settings.top_n = int((data.get("rank") or {}).get("top_n", settings.top_n))
    bot = data.get("bot") or {}
    settings.digest_hours = int(bot.get("digest_hours", settings.digest_hours))
    settings.refresh_hour = int(bot.get("refresh_hour", settings.refresh_hour))

    # Переменная окружения важнее файла: на хостинге секреты задаются в панели.
    admin_id = os.environ.get("ADMIN_ID") or data.get("admin_id")
    if admin_id:
        try:
            settings.admin_id = int(admin_id)
        except (TypeError, ValueError):
            settings.admin_id = None
    return settings
