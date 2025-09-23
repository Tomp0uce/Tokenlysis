"""HTTP client dedicated to the CoinMarketCap Fear & Greed API."""

from __future__ import annotations

import datetime as dt
import json
import logging
import math
import time
from typing import Any

import requests
from requests import Session

from ..core.settings import mask_secret, settings

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://pro-api.coinmarketcap.com"
_LATEST_PATH = "/v3/fear-and-greed/latest"
_HISTORY_PATH = "/v3/fear-and-greed/historical"
_DEFAULT_LABEL = "Unknown"


def _ensure_timezone(ts: dt.datetime) -> dt.datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=dt.timezone.utc)
    return ts.astimezone(dt.timezone.utc)


def _parse_timestamp(raw: object) -> tuple[str, dt.datetime] | None:
    if isinstance(raw, (int, float)):
        if not math.isfinite(raw):
            return None
        parsed = dt.datetime.fromtimestamp(float(raw), tz=dt.timezone.utc)
        return parsed.isoformat(), parsed
    if isinstance(raw, str):
        candidate = raw.strip()
        if not candidate:
            return None
        if candidate.endswith("Z"):
            candidate = f"{candidate[:-1]}+00:00"
        try:
            parsed = dt.datetime.fromisoformat(candidate)
        except ValueError:
            try:
                numeric = float(candidate)
            except ValueError:
                return None
            if not math.isfinite(numeric):
                return None
            parsed = dt.datetime.fromtimestamp(numeric, tz=dt.timezone.utc)
        normalized = _ensure_timezone(parsed)
        return normalized.isoformat(), normalized
    return None


def _parse_score(raw: object) -> int | None:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    clamped = max(0, min(100, int(round(value))))
    return clamped


def _parse_label(raw: object) -> str:
    if raw is None:
        return _DEFAULT_LABEL
    label = str(raw).strip()
    return label or _DEFAULT_LABEL


class CoinMarketCapFearGreedClient:
    """Small wrapper around the CoinMarketCap Fear & Greed v3 endpoints."""

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
                "coinmarketcap auth enabled: X-CMC_PRO_API_KEY=%s", mask_secret(api_key)
            )
        self.throttle_ms = max(0, int(throttle_ms))

    def _request(
        self, path: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
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
            logger.warning(
                "coinmarketcap request failed: %s",
                json.dumps({"url": url, "status": response.status_code, "body": body}),
            )
            raise
        payload: Any = response.json()
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _normalize_entry(
        entry: dict[str, Any],
    ) -> tuple[dict[str, Any], dt.datetime] | None:
        if not isinstance(entry, dict):
            return None
        timestamp_raw = entry.get("timestamp") or entry.get("time")
        parsed_timestamp = _parse_timestamp(timestamp_raw)
        if parsed_timestamp is None:
            return None
        timestamp_str, timestamp_dt = parsed_timestamp
        score_raw = entry.get("score") if "score" in entry else entry.get("value")
        score = _parse_score(score_raw)
        if score is None:
            return None
        label_raw = (
            entry.get("label")
            or entry.get("value_classification")
            or entry.get("valueClassification")
            or entry.get("classification")
        )
        label = _parse_label(label_raw)
        normalized = {"timestamp": timestamp_str, "score": score, "label": label}
        return normalized, timestamp_dt

    def get_latest(self) -> dict[str, Any] | None:
        payload = self._request(_LATEST_PATH)
        data = payload.get("data") if isinstance(payload, dict) else None
        normalized: list[tuple[dict[str, Any], dt.datetime]] = []
        if isinstance(data, dict):
            entry = self._normalize_entry(data)
            if entry:
                normalized.append(entry)
        elif isinstance(data, list):
            for raw in data:
                entry = self._normalize_entry(raw)
                if entry:
                    normalized.append(entry)
        if not normalized:
            return None
        normalized.sort(key=lambda item: item[1])
        return normalized[-1][0]

    def get_historical(
        self,
        *,
        limit: int | None = None,
        time_start: str | None = None,
        time_end: str | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {}
        if limit is not None:
            if limit <= 0:
                raise ValueError("limit must be positive")
            params["limit"] = int(limit)
        if time_start:
            params["time_start"] = str(time_start)
        if time_end:
            params["time_end"] = str(time_end)
        payload = self._request(_HISTORY_PATH, params=params or None)
        data = payload.get("data") if isinstance(payload, dict) else None
        normalized: list[tuple[dict[str, Any], dt.datetime]] = []
        if isinstance(data, dict):
            quotes = data.get("quotes") if isinstance(data, dict) else None
            items = quotes if isinstance(quotes, list) else [data]
        elif isinstance(data, list):
            items = data
        else:
            items = []
        for raw in items:
            entry = self._normalize_entry(raw)
            if entry:
                normalized.append(entry)
        normalized.sort(key=lambda item: item[1])
        return [item[0] for item in normalized]


def build_default_client() -> CoinMarketCapFearGreedClient:
    """Factory used by services to build a configured client."""

    return CoinMarketCapFearGreedClient(
        api_key=settings.CMC_API_KEY,
        base_url=settings.CMC_BASE_URL,
        throttle_ms=settings.CMC_THROTTLE_MS,
    )


__all__ = ["CoinMarketCapFearGreedClient", "build_default_client"]
