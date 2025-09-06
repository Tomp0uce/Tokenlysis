from __future__ import annotations

from typing import Dict, List, Optional

import os

import requests

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
        self.api_key = api_key or os.getenv("COINGECKO_API_KEY")
        if self.api_key:
            self.session.headers.update({"X-Cg-Pro-Api-Key": self.api_key})

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


__all__ = ["CoinGeckoClient", "BASE_URL"]
