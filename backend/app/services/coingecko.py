from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import json
import random
import time
import requests

from ..core.log import logger, request_id_ctx
from ..core.settings import COINGECKO_API_KEY

BASE_URL = "https://api.coingecko.com/api/v3"


class CoinGeckoClient:
    """Minimal client for the public CoinGecko API."""

    def __init__(
        self,
        base_url: str = BASE_URL,
        session: Optional[requests.Session] = None,
        api_key: Optional[str] = None,
        timeout: int = 10,
        max_retries: int = 3,
        price_ttl: int = 90,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()
        key = api_key or COINGECKO_API_KEY
        self.api_key = key
        if key:
            self.session.headers.update({"x-cg-pro-api-key": key})
        self.timeout = timeout
        self.max_retries = max_retries
        self.price_ttl = price_ttl
        self._price_cache: Dict[Tuple[str, str], Tuple[float, dict]] = {}
        self.rate_limit_remaining: Optional[str] = None

    # internal request helper
    def _request(
        self, endpoint: str, params: Optional[dict] = None
    ) -> requests.Response:
        url = f"{self.base_url}{endpoint}"
        retries = 0
        while True:
            start = time.perf_counter()
            try:
                resp = self.session.get(url, params=params, timeout=self.timeout)
            except requests.RequestException:
                if retries < self.max_retries:
                    sleep = (2**retries) + random.random()
                    time.sleep(sleep)
                    retries += 1
                    continue
                raise
            latency_ms = int((time.perf_counter() - start) * 1000)
            self.rate_limit_remaining = resp.headers.get("X-RateLimit-Remaining")
            if resp.status_code in (429,) or resp.status_code >= 500:
                if retries < self.max_retries:
                    sleep = (2**retries) + random.random()
                    time.sleep(sleep)
                    retries += 1
                    continue
            resp.raise_for_status()
            log_payload = {
                "endpoint": endpoint,
                "status": resp.status_code,
                "latency_ms": latency_ms,
                "retries": retries,
                "request_id": request_id_ctx.get() if request_id_ctx else "-",
            }
            logger.info(json.dumps(log_payload))
            return resp

    def ping(self) -> str:
        """Check API status."""
        resp = self._request("/ping")
        data = resp.json()
        return data.get("gecko_says", "")

    def get_simple_price(
        self, coin_ids: List[str], vs_currencies: List[str]
    ) -> Dict[str, Dict[str, float]]:
        """Fetch current price for a list of coins in given currencies."""
        key = ("|".join(sorted(coin_ids)), "|".join(sorted(vs_currencies)))
        now = time.time()
        cached = self._price_cache.get(key)
        if cached and now - cached[0] < self.price_ttl:
            return cached[1]
        params = {"ids": ",".join(coin_ids), "vs_currencies": ",".join(vs_currencies)}
        resp = self._request("/simple/price", params=params)
        data = resp.json()
        self._price_cache[key] = (now, data)
        return data

    def get_markets(
        self,
        vs_currency: str = "usd",
        order: str = "market_cap_desc",
        per_page: int = 20,
        page: int = 1,
    ) -> List[dict]:
        """Return market data for a list of coins."""
        params = {
            "vs_currency": vs_currency,
            "order": order,
            "per_page": per_page,
            "page": page,
        }
        resp = self._request("/coins/markets", params=params)
        return resp.json()

    def get_market_chart(self, coin_id: str, days: int) -> dict:
        """Return historical market chart for a coin."""
        params = {
            "vs_currency": "usd",
            "days": days,
            "interval": "daily",
        }
        resp = self._request(f"/coins/{coin_id.lower()}/market_chart", params=params)
        return resp.json()


__all__ = ["CoinGeckoClient", "BASE_URL"]
