from __future__ import annotations

from typing import Mapping
from urllib.parse import urlparse

from ..models import LatestPrice


def normalize_link(value: object) -> str | None:
    """Return a validated URL or ``None`` when invalid."""

    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if not candidate:
        return None
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"}:
        return None
    if not parsed.netloc:
        return None
    return candidate


def serialize_price(
    price: LatestPrice,
    details: Mapping[str, object] | None,
) -> dict[str, object]:
    """Convert ORM rows and metadata into an API payload."""

    details = details or {}
    names_raw = details.get("category_names") if isinstance(details, Mapping) else []
    ids_raw = details.get("category_ids") if isinstance(details, Mapping) else []
    names = list(names_raw) if isinstance(names_raw, (list, tuple)) else []
    ids = list(ids_raw) if isinstance(ids_raw, (list, tuple)) else []

    raw_name = details.get("name") if isinstance(details, Mapping) else ""
    name = raw_name.strip() if isinstance(raw_name, str) else ""

    raw_symbol = details.get("symbol") if isinstance(details, Mapping) else ""
    symbol = raw_symbol.strip() if isinstance(raw_symbol, str) else ""

    raw_logo = details.get("logo_url") if isinstance(details, Mapping) else None
    logo_url = raw_logo.strip() if isinstance(raw_logo, str) and raw_logo.strip() else None

    raw_links = details.get("social_links") if isinstance(details, Mapping) else {}
    social_links: dict[str, str] = {}
    if isinstance(raw_links, Mapping):
        for key in ("website", "twitter", "reddit", "github", "discord", "telegram"):
            normalized = normalize_link(raw_links.get(key))
            if normalized:
                social_links[key] = normalized

    return {
        "coin_id": price.coin_id,
        "vs_currency": price.vs_currency,
        "price": price.price,
        "market_cap": price.market_cap,
        "fully_diluted_market_cap": price.fully_diluted_market_cap,
        "volume_24h": price.volume_24h,
        "rank": price.rank,
        "pct_change_24h": price.pct_change_24h,
        "pct_change_7d": price.pct_change_7d,
        "pct_change_30d": price.pct_change_30d,
        "snapshot_at": price.snapshot_at,
        "category_names": names,
        "category_ids": ids,
        "name": name,
        "symbol": symbol,
        "logo_url": logo_url,
        "social_links": social_links,
    }


__all__ = ["normalize_link", "serialize_price"]
