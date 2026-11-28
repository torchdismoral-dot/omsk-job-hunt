from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class Vacancy:
    key: str
    source: str
    source_id: str
    title: str
    company: str | None = None
    salary_from: int | None = None
    salary_to: int | None = None
    currency: str = "RUB"
    city: str | None = None
    district: str | None = None
    is_remote: bool = False
    experience: str | None = None
    url: str = ""
    published_at: str | None = None
    description: str | None = None
    lat: float | None = None
    lng: float | None = None
    red_flags: list[str] = field(default_factory=list)


DISTRICTS = ("Кировский", "Центральный")


def _money(value: Any) -> int | None:
    """SuperJob отдаёт 0 вместо «зарплата не указана»."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _iso_date(timestamp: Any) -> str | None:
    if not isinstance(timestamp, (int, float)) or timestamp <= 0:
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).date().isoformat()


def _coord(value: Any) -> float | None:
    """SuperJob отдаёт 0, когда координат нет."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number != 0 else None


def _district(text: str) -> str | None:
    lowered = text.lower()
    for name in DISTRICTS:
        if name.lower() in lowered:
            return name
    return None


def _city_from_location(location: str) -> str | None:
    for part in location.replace(";", ",").split(","):
        part = part.strip()
        if part.startswith("г. "):
            return part[3:].strip()
        if part.startswith("г "):
            return part[2:].strip()
    return None


def _trudvsem_experience(raw: Any) -> str | None:
    """В открытых данных trudvsem опыт — целое число лет (0, 1, 6, ...)."""
    if raw is None:
        return None
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None
        if not text.isdigit():
            return text
        raw = int(text)
    try:
        years = int(raw)
    except (TypeError, ValueError):
        return None
    if years <= 0:
        return "Без опыта"
    if years == 1:
        return "От 1 года"
    return f"От {years} лет"


def from_superjob(obj: dict) -> Vacancy:
    town = obj.get("town") or {}
    place = obj.get("place_of_work") or {}
    experience = obj.get("experience") or {}
    title = (obj.get("profession") or "").strip()
    address = obj.get("address") or ""
    description = " ".join(
        part for part in (obj.get("work"), obj.get("candidat")) if part
    )
    return Vacancy(
        key=f"superjob:{obj['id']}",
        source="superjob",
        source_id=str(obj["id"]),
        title=title,
        company=obj.get("firm_name") or None,
        salary_from=_money(obj.get("payment_from")),
        salary_to=_money(obj.get("payment_to")),
        currency=(obj.get("currency") or "rub").upper(),
        city=town.get("title") or None,
        district=_district(f"{address} {title}"),
        is_remote=place.get("id") == 2,
        experience=experience.get("title"),
        url=obj.get("link") or "",
        published_at=_iso_date(obj.get("date_published")),
        description=description or None,
        lat=_coord(obj.get("latitude")),
        lng=_coord(obj.get("longitude")),
    )


def from_trudvsem(vac: dict) -> Vacancy:
    requirement = vac.get("requirement") or {}
    company = vac.get("company") or {}
    addresses = (vac.get("addresses") or {}).get("address") or []
    location = addresses[0].get("location") if addresses else ""
    title = (vac.get("job-name") or "").strip()
    schedule = (vac.get("schedule") or "").lower()
    description = " ".join(
        part for part in (vac.get("duty"), vac.get("requirements")) if part
    )
    return Vacancy(
        key=f"trudvsem:{vac['id']}",
        source="trudvsem",
        source_id=str(vac["id"]),
        title=title,
        company=company.get("name") or None,
        salary_from=_money(vac.get("salary_min")),
        salary_to=_money(vac.get("salary_max")),
        currency="RUB",
        city=_city_from_location(location or ""),
        district=_district(f"{location} {title}"),
        is_remote="удалённ" in schedule or "дистанц" in schedule,
        experience=_trudvsem_experience(requirement.get("experience")),
        url=vac.get("vac_url") or "",
        published_at=vac.get("creation-date") or None,
        description=description or None,
        lat=_coord(addresses[0].get("lat")) if addresses else None,
        lng=_coord(addresses[0].get("lng")) if addresses else None,
    )

# hh отдаёт опыт кодовым значением, а не подписью: приводим к формату SuperJob,
# иначе фильтр allowed_experience в filters.py не совпадёт.
HH_EXPERIENCE = {
    "noExperience": "Без опыта",
    "between1And3": "От 1 года",
    "between3And6": "От 3 лет",
    "moreThan6": "От 6 лет",
}

# hh шифрует валюты своими кодами: RUR — это рубль до 2007 года.
HH_CURRENCY = {"RUR": "RUB", "UAH": "UAH", "USD": "USD", "EUR": "EUR", "KZT": "KZT"}


def _hh_formats(raw: Any) -> list[str]:
    """workFormats приходит списком {'workFormatsElement': ['REMOTE', ...]}."""
    formats: list[str] = []
    for block in raw or []:
        if isinstance(block, dict):
            formats.extend(str(item) for item in block.get("workFormatsElement") or [])
    return formats


def _hh_currency(code: Any) -> str:
    code = str(code or "RUR").upper()
    return HH_CURRENCY.get(code, code)


def from_hh(obj: dict) -> Vacancy:
    """Карточка выдачи hh.ru: описания в ней нет, только заголовок и компания."""
    company = obj.get("company") or {}
    compensation = obj.get("compensation") or {}
    area = obj.get("area") or {}
    address = obj.get("address") or {}
    marker = address.get("marker") or {}
    links = obj.get("links") or {}
    published = obj.get("publicationTime") or {}
    vacancy_id = obj["vacancyId"]
    title = (obj.get("name") or "").strip()
    address_text = address.get("displayName") or ""
    if not isinstance(published, dict):
        published = {}
    return Vacancy(
        key=f"hh:{vacancy_id}",
        source="hh",
        source_id=str(vacancy_id),
        title=title,
        company=company.get("visibleName") or company.get("name") or None,
        salary_from=_money(compensation.get("from")),
        salary_to=_money(compensation.get("to")),
        currency=_hh_currency(compensation.get("currencyCode")),
        city=area.get("name") or None,
        district=_district(f"{address_text} {title}"),
        is_remote="REMOTE" in _hh_formats(obj.get("workFormats")),
        experience=HH_EXPERIENCE.get(str(obj.get("workExperience") or "")),
        url=links.get("desktop") or f"https://hh.ru/vacancy/{vacancy_id}",
        published_at=_iso_date(published.get("@timestamp")),
        description=None,
        lat=_coord(marker.get("@lat")),
        lng=_coord(marker.get("@lng")),
    )

