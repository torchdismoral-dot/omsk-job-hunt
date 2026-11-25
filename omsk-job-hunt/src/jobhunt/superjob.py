from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request


class SuperJobError(RuntimeError):
    pass


class SuperJobClient:
    def __init__(
        self,
        key: str,
        base_url: str = "https://api.superjob.ru/2.0",
        page_size: int = 40,
        delay_ms: int = 300,
    ):
        if not key:
            raise SuperJobError("SUPERJOB_KEY не задан")
        self.key = key
        self.base_url = base_url.rstrip("/")
        self.page_size = min(page_size, 40)
        self.delay = delay_ms / 1000

    def _get(self, path: str, params: dict) -> dict:
        url = f"{self.base_url}/{path}?" + urllib.parse.urlencode(params, encoding="utf-8")
        request = urllib.request.Request(
            url,
            headers={
                "X-Api-App-Id": self.key,
                "User-Agent": "OmskJobHunt/1.0",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                data = json.load(response)
        except urllib.error.HTTPError as exc:
            raise SuperJobError(f"HTTP {exc.code} на {path}") from exc
        if isinstance(data, dict) and "error" in data:
            raise SuperJobError(str(data["error"]))
        return data

    def fetch_all(self, max_pages: int = 20, **params) -> list[dict]:
        collected: list[dict] = []
        for page in range(max_pages):
            data = self._get(
                "vacancies/", {**params, "page": page, "count": self.page_size}
            )
            objects = data.get("objects") or []
            collected.extend(objects)
            if not objects or not data.get("more"):
                break
            time.sleep(self.delay)
        return collected
