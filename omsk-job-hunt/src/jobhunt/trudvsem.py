from __future__ import annotations

import json
import urllib.error
import urllib.request


class TrudvsemError(RuntimeError):
    pass


class TrudvsemClient:
    def __init__(
        self,
        base_url: str = "https://opendata.trudvsem.ru/api/v1",
        region: str = "5500000000000",
        limit: int = 150,
    ):
        self.base_url = base_url.rstrip("/")
        self.region = region
        self.limit = limit

    def fetch_all(self) -> list[dict]:
        """offset у trudvsem упирается в ~150: видно только начало выдачи."""
        url = f"{self.base_url}/vacancies/region/{self.region}?offset=0&limit={self.limit}"
        request = urllib.request.Request(url, headers={"User-Agent": "OmskJobHunt/1.0"})
        try:
            with urllib.request.urlopen(request, timeout=40) as response:
                data = json.load(response)
        except urllib.error.HTTPError as exc:
            raise TrudvsemError(f"HTTP {exc.code} на trudvsem") from exc
        vacancies = (data.get("results") or {}).get("vacancies") or []
        return [item["vacancy"] for item in vacancies if "vacancy" in item]
