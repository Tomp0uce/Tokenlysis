from __future__ import annotations

from typing import Dict, List, Optional

import requests

from ..core.settings import get_coingecko_headers

BASE_URL = "https://api.coingecko.com/api/v3"


class CoinGeckoClient:
    """Minimal client for the public CoinGecko API."""

    def __init__(
        self,
        base_url: str = BASE_URL,
        session: Optional[requests.Session] = None,
        api_key: Optional[str] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()
        headers = {"x-cg-pro-api-key": api_key} if api_key else get_coingecko_headers()
        self.api_key = headers.get("x-cg-pro-api-key")
        if headers:
            self.session.headers.update(headers)

    def ping(self) -> str:
        """Check API status."""
        url = f"{self.base_url}/ping"
        resp = self.session.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return data.get("gecko_says", "")

    def get_simple_price(
        self, coin_ids: List[str], vs_currencies: List[str]
    ) -> Dict[str, Dict[str, float]]:
        """Fetch current price for a list of coins in given currencies."""
        url = f"{self.base_url}/simple/price"
        params = {"ids": ",".join(coin_ids), "vs_currencies": ",".join(vs_currencies)}
        resp = self.session.get(url, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def get_markets(
        self,
        vs_currency: str = "usd",
        order: str = "market_cap_desc",
        per_page: int = 20,
        page: int = 1,
    ) -> List[dict]:
        """Return market data for a list of coins."""
        url = f"{self.base_url}/coins/markets"
        params = {
            "vs_currency": vs_currency,
            "order": order,
            "per_page": per_page,
            "page": page,
        }
        resp = self.session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def get_market_chart(self, coin_id: str, days: int) -> dict:
        """Return historical market chart for a coin."""
        url = f"{self.base_url}/coins/{coin_id}/market_chart"
        params = {
            "vs_currency": "usd",
            "days": days,
            "interval": "daily",
        }
        resp = self.session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()


__all__ = ["CoinGeckoClient", "BASE_URL"]
