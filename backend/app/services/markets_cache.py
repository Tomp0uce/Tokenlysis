from __future__ import annotations

import datetime as dt
import threading
from dataclasses import dataclass
from typing import Dict, List

from sqlalchemy.orm import Session

from ..core.settings import settings
from .dao import CoinsRepo, MetaRepo, PricesRepo
from .serialization import serialize_price


@dataclass
class MarketsPayload:
    """Cached markets payload shared by front-facing endpoints."""

    items: List[dict[str, object]]
    last_refresh_at: str | None
    data_source: str | None
    stale: bool
    price_index: Dict[str, dict[str, object]]


@dataclass
class _CacheEntry:
    payload: MarketsPayload
    expires_at: dt.datetime


class MarketsCache:
    """In-memory TTL cache for aggregated market data."""

    def __init__(self, ttl_seconds: int = 90) -> None:
        if ttl_seconds < 1:
            raise ValueError("ttl_seconds must be >= 1")
        self._ttl_seconds = ttl_seconds
        self._cache: dict[str, _CacheEntry] = {}
        self._lock = threading.Lock()

    def _now(self) -> dt.datetime:
        return dt.datetime.now(dt.timezone.utc)

    def invalidate(self, vs: str | None = None) -> None:
        """Invalidate cache entries for ``vs`` or the entire cache when ``None``."""

        with self._lock:
            if vs is None:
                self._cache.clear()
            else:
                self._cache.pop(vs.lower(), None)

    def _compute_stale(self, last_refresh_at: str | None) -> bool:
        if not last_refresh_at:
            return True
        try:
            ts = dt.datetime.fromisoformat(last_refresh_at)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=dt.timezone.utc)
            return (self._now() - ts) > dt.timedelta(hours=24)
        except Exception:  # pragma: no cover - defensive
            return True

    def _build_snapshot(self, session: Session, vs: str) -> MarketsPayload:
        prices_repo = PricesRepo(session)
        coins_repo = CoinsRepo(session)
        meta_repo = MetaRepo(session)
        limit = max(settings.CG_TOP_N, 1)
        rows = prices_repo.get_top(vs, limit)
        coin_ids = [row.coin_id for row in rows]
        details_map = coins_repo.get_details_bulk(coin_ids)
        items = [serialize_price(row, details_map.get(row.coin_id, {})) for row in rows]
        last_refresh_at = meta_repo.get("last_refresh_at")
        data_source = meta_repo.get("data_source")
        stale = self._compute_stale(last_refresh_at)
        price_index = {item["coin_id"]: item for item in items}
        return MarketsPayload(
            items=items,
            last_refresh_at=last_refresh_at,
            data_source=data_source,
            stale=stale,
            price_index=price_index,
        )

    def _get_snapshot(self, session: Session, vs: str) -> MarketsPayload:
        key = vs.lower()
        now = self._now()
        with self._lock:
            entry = self._cache.get(key)
            if entry and entry.expires_at > now:
                return entry.payload
        payload = self._build_snapshot(session, key)
        expires_at = self._now() + dt.timedelta(seconds=self._ttl_seconds)
        with self._lock:
            self._cache[key] = _CacheEntry(payload=payload, expires_at=expires_at)
        return payload

    def _refresh_if_meta_changed(
        self, session: Session, vs: str, snapshot: MarketsPayload
    ) -> MarketsPayload:
        meta_repo = MetaRepo(session)
        last_refresh_at = meta_repo.get("last_refresh_at")
        data_source = meta_repo.get("data_source")
        if (
            last_refresh_at == snapshot.last_refresh_at
            and data_source == snapshot.data_source
        ):
            return snapshot
        payload = self._build_snapshot(session, vs)
        expires_at = self._now() + dt.timedelta(seconds=self._ttl_seconds)
        with self._lock:
            self._cache[vs.lower()] = _CacheEntry(payload=payload, expires_at=expires_at)
        return payload

    def get_top(self, session: Session, vs: str, limit: int) -> dict[str, object]:
        snapshot = self._get_snapshot(session, vs)
        snapshot = self._refresh_if_meta_changed(session, vs, snapshot)
        limited = [item.copy() for item in snapshot.items[: max(limit, 0)]]
        return {
            "items": limited,
            "last_refresh_at": snapshot.last_refresh_at,
            "data_source": snapshot.data_source,
            "stale": self._compute_stale(snapshot.last_refresh_at),
        }

    def get_price(
        self, session: Session, vs: str, coin_id: str
    ) -> dict[str, object] | None:
        snapshot = self._get_snapshot(session, vs)
        cached = snapshot.price_index.get(coin_id)
        if cached is not None:
            return cached.copy()

        prices_repo = PricesRepo(session)
        row = prices_repo.get_price(coin_id, vs)
        if row is None:
            return None
        coins_repo = CoinsRepo(session)
        details = coins_repo.get_details(coin_id)
        payload = serialize_price(row, details)
        with self._lock:
            entry = self._cache.get(vs.lower())
            if entry and entry.payload is snapshot:
                entry.payload.price_index[coin_id] = payload
        return payload


__all__ = ["MarketsCache", "MarketsPayload"]
