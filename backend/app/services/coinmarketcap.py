"""HTTP client wrapper for CoinMarketCap Fear & Greed endpoints."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import requests
from requests import Session

from ..core.settings import mask_secret, settings

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://pro-api.coinmarketcap.com"
_FEAR_GREED_ENDPOINT = "/v1/cryptocurrency/trending/fear-and-greed"
_FEAR_GREED_HISTORY_ENDPOINT = f"{_FEAR_GREED_ENDPOINT}/historical"


class CoinMarketCapClient:
    """Minimal client for the CoinMarketCap API."""

    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str | None = None,
        throttle_ms: int = 1000,
        session: Session | None = None,
    ) -> None:
        self.base_url = (base_url or _DEFAULT_BASE_URL).rstrip("/")
        self.session = session or requests.Session()
        self.session.headers.update(
            {"Accept": "application/json", "User-Agent": "Tokenlysis/1.0"}
        )
        if api_key:
            self.session.headers["X-CMC_PRO_API_KEY"] = api_key
            logger.info(
                "coinmarketcap auth enabled: X-CMC_PRO_API_KEY=%s",
                mask_secret(api_key),
            )
        self.throttle_ms = max(0, int(throttle_ms))

    def _request(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        if self.throttle_ms:
            time.sleep(self.throttle_ms / 1000.0)
        response = self.session.get(url, params=params, timeout=(3.1, 20))
        try:
            response.raise_for_status()
        except requests.HTTPError:
            try:
                body = response.json()
            except Exception:  # pragma: no cover - defensive logging
                body = response.text
            logger.warning("coinmarketcap request failed: %s", json.dumps({
                "url": url,
                "status": response.status_code,
                "body": body,
            }))
            raise
        return response.json()

    def get_fear_greed_latest(self) -> dict[str, Any] | None:
        payload = self._request(_FEAR_GREED_ENDPOINT)
        data = payload.get("data") if isinstance(payload, dict) else None
        if isinstance(data, dict):
            return data
        if isinstance(data, list):
            return data[-1] if data else None
        return None

    def get_fear_greed_history(self) -> list[dict[str, Any]]:
        payload = self._request(_FEAR_GREED_HISTORY_ENDPOINT)
        data: Any = payload.get("data") if isinstance(payload, dict) else None
        if isinstance(data, dict):
            quotes = data.get("quotes")
            if isinstance(quotes, list):
                normalized: list[dict[str, Any]] = []
                for quote in quotes:
                    if isinstance(quote, dict):
                        value_block = quote.get("value")
                        if isinstance(value_block, dict):
                            normalized.append(value_block)
                        else:
                            normalized.append(quote)
                return normalized
        if isinstance(data, list):
            return [entry for entry in data if isinstance(entry, dict)]
        return []


def build_default_client() -> CoinMarketCapClient:
    """Factory used by services to build a configured client."""

    return CoinMarketCapClient(
        api_key=settings.CMC_API_KEY,
        base_url=settings.CMC_BASE_URL,
        throttle_ms=settings.CMC_THROTTLE_MS,
    )


__all__ = ["CoinMarketCapClient", "build_default_client"]
