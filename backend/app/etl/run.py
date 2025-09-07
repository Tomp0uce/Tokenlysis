"""Fetch market data from CoinGecko and persist into the database."""

from __future__ import annotations

import datetime as dt
import json
import logging
from pathlib import Path

import requests

from ..core.settings import settings, effective_coingecko_base_url
from ..services.budget import CallBudget
from ..services.coingecko import CoinGeckoClient
from ..services.dao import PricesRepo, MetaRepo
from ..db import SessionLocal

logger = logging.getLogger(__name__)


class DataUnavailable(Exception):
    """Raised when live data could not be fetched."""


def _fetch_markets(
    client: CoinGeckoClient,
    limit: int,
    per_page_max: int,
    budget: CallBudget | None,
) -> tuple[list[dict], int]:
    per_page = min(per_page_max, 250)
    coins: list[dict] = []
    page = 1
    calls = 0
    while len(coins) < limit:
        if budget and not budget.can_spend(1):
            logger.warning(
                "quota exceeded",
                extra={"monthly_call_count": budget.monthly_call_count},
            )
            raise DataUnavailable("quota exceeded")
        try:
            data = client.get_markets(vs="usd", per_page=per_page, page=page)
        except requests.HTTPError as exc:
            calls += 1
            if budget:
                budget.spend(1)
            status = exc.response.status_code if exc.response is not None else 0
            if 400 <= status < 500 and per_page > 100:
                per_page = 100
                continue
            raise
        calls += 1
        if budget:
            budget.spend(1)
        if not data:
            break
        coins.extend(data)
        page += 1
        if len(data) < per_page:
            break
    return coins[:limit], calls


def _seed_rows() -> list[dict]:
    path = Path(settings.SEED_FILE)
    with path.open() as f:
        return json.load(f)


def run_etl(
    *,
    client: CoinGeckoClient | None = None,
    budget: CallBudget | None = None,
) -> int:
    """Fetch markets and persist them. Returns number of rows processed."""

    if client is None:
        client = CoinGeckoClient(
            base_url=effective_coingecko_base_url(),
            api_key=settings.COINGECKO_API_KEY or settings.coingecko_api_key,
        )

    limit = max(10, settings.CG_TOP_N)
    per_page_max = settings.CG_PER_PAGE_MAX
    try:
        markets, calls = _fetch_markets(client, limit, per_page_max, budget)
    except DataUnavailable:
        raise
    except Exception as exc:  # pragma: no cover - network failures
        logger.exception("market fetch failed: %s", exc)
        raise DataUnavailable("fetch failed") from exc

    now = dt.datetime.now(dt.timezone.utc)
    price_rows = [
        {
            "coin_id": c["id"],
            "vs_currency": "usd",
            "price": c.get("current_price"),
            "market_cap": c.get("market_cap"),
            "volume_24h": c.get("total_volume"),
            "rank": c.get("market_cap_rank"),
            "pct_change_24h": c.get("price_change_percentage_24h"),
            "snapshot_at": now,
        }
        for c in markets
    ]

    session = SessionLocal()
    prices_repo = PricesRepo(session)
    meta_repo = MetaRepo(session)
    try:
        prices_repo.upsert_latest(price_rows)
        prices_repo.insert_snapshot(price_rows)
        meta_repo.set("last_refresh_at", now.isoformat())
        meta_repo.set("last_etl_items", str(len(price_rows)))
        if budget:
            meta_repo.set("monthly_call_count", str(budget.monthly_call_count))
        meta_repo.set("data_source", "api")
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    logger.info(
        json.dumps(
            {
                "event": "etl run completed",
                "coingecko_calls_total": calls,
                "monthly_call_count": budget.monthly_call_count if budget else None,
                "last_refresh_at": now.isoformat(),
                "rows": len(price_rows),
            }
        )
    )

    return len(price_rows)


def load_seed() -> None:
    """Load seed data into the database."""

    rows = _seed_rows()
    now = dt.datetime.now(dt.timezone.utc)
    price_rows = [
        {
            "coin_id": r["id"],
            "vs_currency": "usd",
            "price": r.get("price"),
            "market_cap": r.get("market_cap"),
            "volume_24h": r.get("volume_24h"),
            "rank": r.get("rank"),
            "pct_change_24h": r.get("pct_change_24h"),
            "snapshot_at": now,
        }
        for r in rows
    ]
    session = SessionLocal()
    prices_repo = PricesRepo(session)
    meta_repo = MetaRepo(session)
    try:
        prices_repo.upsert_latest(price_rows)
        prices_repo.insert_snapshot(price_rows)
        meta_repo.set("last_refresh_at", now.isoformat())
        meta_repo.set("last_etl_items", str(len(price_rows)))
        meta_repo.set("data_source", "seed")
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
