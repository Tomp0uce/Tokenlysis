import json
import logging
import time
from typing import List

import requests

from ..core.settings import settings

logger = logging.getLogger(__name__)

PRO_BASE = "https://pro-api.coingecko.com/api/v3"
PUB_BASE = "https://api.coingecko.com/api/v3"


class CoinGeckoClient:
    """HTTP client for the CoinGecko API with throttling and retries."""

    def __init__(
        self,
        base_url: str,
        api_key: str | None,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()
        self.session.headers.update(
            {"Accept": "application/json", "User-Agent": "tokenlysis/1.0"}
        )
        if api_key:
            self.session.headers.update({"x-cg-pro-api-key": api_key})
        self.api_key = api_key

    def _request(self, path: str, params: dict | None = None) -> requests.Response:
        url = f"{self.base_url}{path}"
        time.sleep(settings.CG_THROTTLE_MS / 1000.0)
        for attempt in range(1, 6):
            t0 = time.perf_counter()
            resp = self.session.get(url, params=params, timeout=(3.1, 20))
            latency = int((time.perf_counter() - t0) * 1000)
            rid = resp.headers.get("X-Request-Id", "-")
            logger.info(
                json.dumps(
                    {
                        "endpoint": path,
                        "status": resp.status_code,
                        "latency_ms": latency,
                        "retries": attempt - 1,
                        "request_id": rid,
                    }
                )
            )
            if resp.status_code == 429:
                ra = resp.headers.get("Retry-After")
                sleep_s = float(ra) if ra else min(2**attempt, 16)
                time.sleep(sleep_s)
                continue
            resp.raise_for_status()
            return resp
        resp.raise_for_status()
        return resp

    def ping(self) -> str:
        return self._request("/ping").json().get("gecko_says", "")

    def get_simple_price(self, coin_ids: List[str], vs_currencies: List[str]) -> dict:
        params = {"ids": ",".join(coin_ids), "vs_currencies": ",".join(vs_currencies)}
        return self._request("/simple/price", params).json()

    def get_markets(
        self,
        vs: str = "usd",
        order: str = "market_cap_desc",
        per_page: int = 100,
        page: int = 1,
    ) -> List[dict]:
        params = {"vs_currency": vs, "order": order, "per_page": per_page, "page": page}
        return self._request("/coins/markets", params).json()

    def get_market_chart(
        self, coin_id: str, days: int, vs: str = "usd", interval: str | None = None
    ) -> dict:
        params = {"vs_currency": vs, "days": days, "interval": interval or "daily"}
        return self._request(f"/coins/{coin_id.lower()}/market_chart", params).json()
