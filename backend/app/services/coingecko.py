import time
import logging
from typing import List, Dict, Optional

import requests
from requests.adapters import HTTPAdapter, Retry

from ..core.settings import settings


class CoinGeckoClient:
    """HTTP client for the CoinGecko API with retries and backoff."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        session: Optional[requests.Session] = None,
        max_retries: int = 5,
        price_ttl: int = 90,
    ) -> None:
        self.base_url = (base_url or settings.COINGECKO_BASE_URL).rstrip("/")
        self.sess = session or requests.Session()

        retries = Retry(
            total=max_retries,
            backoff_factor=0.8,
            status_forcelist=(429, 500, 502, 503, 504),
            respect_retry_after_header=True,
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retries)
        self.sess.mount("https://", adapter)
        self.sess.mount("http://", adapter)

        key = api_key or settings.COINGECKO_API_KEY
        self.headers = {
            "Accept": "application/json",
            "User-Agent": "tokenlysis/1.0",
        }
        if key:
            # Support both demo and pro headers
            self.headers["x-cg-pro-api-key"] = key
            self.headers["x-cg-demo-api-key"] = key

        self.price_ttl = price_ttl
        self._price_cache: Dict[tuple[str, str], tuple[float, dict]] = {}

    def _request(self, path: str, params: dict | None = None) -> Dict:
        url = f"{self.base_url}{path}"
        t0 = time.time()
        resp = self.sess.get(url, params=params or {}, headers=self.headers, timeout=30)

        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After")
            logging.warning(f"CoinGecko 429; retry_after={retry_after}, url={resp.url}")
        if not 200 <= resp.status_code < 300:
            logging.error(
                "CoinGecko error",
                extra={
                    "status": resp.status_code,
                    "url": resp.url,
                    "body": resp.text[:500],
                },
            )
            resp.raise_for_status()

        latency_ms = int((time.time() - t0) * 1000)
        logging.info(
            "CG call",
            extra={
                "endpoint": path,
                "status": resp.status_code,
                "latency_ms": latency_ms,
            },
        )
        return resp.json()

    def ping(self) -> str:
        data = self._request("/ping")
        return data.get("gecko_says", "")

    def get_simple_price(self, coin_ids: List[str], vs_currencies: List[str]) -> Dict:
        key = ("|".join(sorted(coin_ids)), "|".join(sorted(vs_currencies)))
        now = time.time()
        cached = self._price_cache.get(key)
        if cached and now - cached[0] < self.price_ttl:
            return cached[1]
        params = {"ids": ",".join(coin_ids), "vs_currencies": ",".join(vs_currencies)}
        data = self._request("/simple/price", params=params)
        self._price_cache[key] = (now, data)
        return data

    def get_markets(
        self,
        vs: str = "usd",
        order: str = "market_cap_desc",
        per_page: int = 100,
        page: int = 1,
    ) -> List[Dict]:
        params = {"vs_currency": vs, "order": order, "per_page": per_page, "page": page}
        return self._request("/coins/markets", params=params)

    def get_market_chart(
        self, coin_id: str, days: int, vs: str = "usd", interval: str | None = None
    ) -> Dict:
        params = {"vs_currency": vs, "days": days}
        if interval:
            params["interval"] = interval
        return self._request(f"/coins/{coin_id.lower()}/market_chart", params=params)
