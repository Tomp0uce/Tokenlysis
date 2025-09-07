import logging
import time
from typing import Dict, List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

PRO_BASE = "https://pro-api.coingecko.com/api/v3"
PUB_BASE = "https://api.coingecko.com/api/v3"


def _clean(s: str | None) -> str | None:
    return s.strip() if isinstance(s, str) else s


class CoinGeckoClient:
    """HTTP client for the CoinGecko API with retry/backoff and caching."""

    def __init__(
        self,
        api_key: str | None = None,
        timeout: int = 12,
        max_retries: int = 3,
        session: Optional[requests.Session] = None,
        price_ttl: int = 90,
    ) -> None:
        self.api_key = _clean(api_key) or None
        self.base_url = PRO_BASE if self.api_key else PUB_BASE

        self.session = session or requests.Session()
        retries = Retry(
            total=max_retries,
            backoff_factor=1.5,
            status_forcelist=[429, 500, 502, 503, 504],
            respect_retry_after_header=True,
        )
        adapter = HTTPAdapter(max_retries=retries)
        self.session.mount("https://", adapter)
        self.session.headers.update(
            {
                "Accept": "application/json",
                "User-Agent": "Tokenlysis/ETL (+github.com/Tomp0uce/Tokenlysis)",
            }
        )
        if self.api_key:
            self.session.headers["x-cg-pro-api-key"] = self.api_key
        self.timeout = timeout

        self._price_cache: Dict[tuple[str, str], tuple[float, dict]] = {}
        self.price_ttl = price_ttl
        self._markets_cache: Dict[tuple[int, int, str], tuple[float, List[dict]]] = {}
        self.market_ttl = 300
        self._chart_cache: Dict[tuple[str, int, str], tuple[float, dict]] = {}
        self.chart_ttl = 900

    def _request(self, path: str, params: dict | None = None) -> dict:
        url = f"{self.base_url}{path}"
        resp = self.session.get(url, params=params, timeout=self.timeout)
        if resp.status_code == 429 and "Retry-After" not in resp.headers:
            time.sleep(2)
            resp = self.session.get(url, params=params, timeout=self.timeout)
        try:
            resp.raise_for_status()
        except requests.HTTPError:
            logger.warning(
                "CG %s %s -> %s %s",
                resp.request.method,
                resp.url,
                resp.status_code,
                resp.text[:300],
            )
            raise
        return resp.json()

    def ping(self) -> str:
        data = self._request("/ping")
        return data.get("gecko_says", "")

    def get_simple_price(self, coin_ids: List[str], vs_currencies: List[str]) -> dict:
        key = ("|".join(sorted(coin_ids)), "|".join(sorted(vs_currencies)))
        now = time.time()
        cached = self._price_cache.get(key)
        if cached and now - cached[0] < self.price_ttl:
            return cached[1]
        params = {"ids": ",".join(coin_ids), "vs_currencies": ",".join(vs_currencies)}
        data = self._request("/simple/price", params)
        self._price_cache[key] = (now, data)
        return data

    def get_markets(
        self, per_page: int = 50, page: int = 1, vs_currency: str = "usd"
    ) -> List[dict]:
        per_page = max(1, min(int(per_page), 250))
        key = (per_page, page, vs_currency)
        now = time.time()
        cached = self._markets_cache.get(key)
        if cached and now - cached[0] < self.market_ttl:
            return cached[1]
        params = {
            "vs_currency": vs_currency,
            "order": "market_cap_desc",
            "per_page": per_page,
            "page": page,
        }
        data = self._request("/coins/markets", params)
        self._markets_cache[key] = (now, data)
        return data

    def get_market_chart(
        self, coin_id: str, days: int, vs_currency: str = "usd"
    ) -> dict:
        days = int(days)
        key = (coin_id.lower(), days, vs_currency)
        now = time.time()
        cached = self._chart_cache.get(key)
        if cached and now - cached[0] < self.chart_ttl:
            return cached[1]
        params = {"vs_currency": vs_currency, "days": str(days)}
        if days >= 2:
            params["interval"] = "daily"
        data = self._request(f"/coins/{coin_id.lower()}/market_chart", params)
        self._chart_cache[key] = (now, data)
        return data
