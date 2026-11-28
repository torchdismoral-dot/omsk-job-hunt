"""Коллектор hh.ru.

Публичный API hh.ru закрыт для соискателей: /vacancies отдаёт 403 при любом
User-Agent (проверено 28.11.2026). Страница выдачи при этом отдаётся по обычному
HTTP и содержит всю выборку в JSON-блобе:

    <template id="HH-Lux-InitialState"> ... vacancySearchResult.vacancies ... </template>

Поэтому Playwright не нужен: один GET на страницу, ~50 вакансий в структуре,
поля проще и стабильнее, чем выковыривать их из разметки.
"""

from __future__ import annotations

import html as html_lib
import json
import time
import urllib.error
import urllib.parse
import urllib.request

TEMPLATE_ID = "HH-Lux-InitialState"
# Выдача отдаётся только «браузерным» запросом: urllib-овский UA hh режет.
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
SEARCH_PATH = "/search/vacancy"


class HHError(RuntimeError):
    pass


def extract_state(page: str) -> dict:
    """Достаёт vacancySearchResult из JSON-состояния страницы выдачи."""
    start = page.find(TEMPLATE_ID)
    if start < 0:
        raise HHError("hh: в ответе нет HH-Lux-InitialState — похоже на заглушку или капчу")
    tag_end = page.find(">", start)
    block_end = page.find("</template", tag_end)
    if tag_end < 0 or block_end < 0:
        raise HHError("hh: блок HH-Lux-InitialState не закрыт")
    raw = html_lib.unescape(page[tag_end + 1 : block_end])
    try:
        state = json.loads(raw)
    except ValueError as exc:
        raise HHError("hh: HH-Lux-InitialState не разбирается как JSON") from exc
    result = state.get("vacancySearchResult")
    if not isinstance(result, dict):
        raise HHError("hh: в состоянии нет vacancySearchResult")
    return result


def parse_vacancies(state: dict) -> list[dict]:
    """Сырые карточки без рекламы: платные вставки ведут на adsrv и чужие регионы."""
    cards: list[dict] = []
    for item in state.get("vacancies") or []:
        if not isinstance(item, dict):
            continue
        if item.get("@isAdv"):
            continue
        if not item.get("vacancyId") or not (item.get("name") or "").strip():
            continue
        cards.append(item)
    return cards


def last_page(state: dict) -> int:
    """Номер последней страницы из paging; 0, если выдача одностраничная."""
    paging = state.get("paging") or {}
    tail = paging.get("lastPage") or {}
    try:
        return int(tail.get("page", 0))
    except (TypeError, ValueError):
        return 0


class HHClient:
    def __init__(
        self,
        area: int = 68,
        base_url: str = "https://hh.ru",
        remote: bool = False,
        experience: str = "noExperience",
        search_period_days: int = 2,
        max_pages: int = 15,
        delay_ms: int = 1500,
        user_agent: str = DEFAULT_UA,
        proxy: str | None = None,
        timeout: int = 40,
    ):
        self.base_url = base_url.rstrip("/")
        self.area = area
        self.remote = remote
        self.experience = experience
        self.search_period_days = search_period_days
        self.max_pages = max(0, max_pages)
        self.delay = max(0, delay_ms) / 1000
        self.user_agent = user_agent
        self.timeout = timeout
        # Прокси опционален: с датацентрового IP Amvera hh отвечает 403.
        handlers = [urllib.request.ProxyHandler({"http": proxy, "https": proxy})] if proxy else []
        self._opener = urllib.request.build_opener(*handlers)

    def _params(self, page: int) -> dict:
        params = {
            "text": "",
            "area": self.area,
            "search_period": self.search_period_days,
            "order_by": "publication_time",
            "page": page,
        }
        if self.experience:
            params["experience"] = self.experience
        if self.remote:
            params["work_format"] = "REMOTE"
        return params

    def _get(self, params: dict) -> str:
        query = urllib.parse.urlencode(params, encoding="utf-8")
        request = urllib.request.Request(
            f"{self.base_url}{SEARCH_PATH}?{query}",
            headers={
                "User-Agent": self.user_agent,
                "Accept-Language": "ru-RU,ru;q=0.9",
                "Accept": "text/html,application/xhtml+xml",
            },
        )
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                return response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            raise HHError(f"hh: HTTP {exc.code} на {SEARCH_PATH}") from exc
        except urllib.error.URLError as exc:
            raise HHError(f"hh: нет связи с {self.base_url} ({exc.reason})") from exc

    def fetch_all(self) -> list[dict]:
        """Карточки с страниц 0..max_pages-1, с остановкой на lastPage и дедупом по id."""
        collected: list[dict] = []
        seen: set[str] = set()
        for page in range(self.max_pages):
            state = extract_state(self._get(self._params(page)))
            cards = parse_vacancies(state)
            for card in cards:
                key = str(card["vacancyId"])
                if key in seen:
                    continue
                seen.add(key)
                collected.append(card)
            if not cards or page >= last_page(state):
                break
            if self.delay:
                time.sleep(self.delay)
        return collected
