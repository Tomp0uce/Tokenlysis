"""Fetch market data from CoinGecko and persist into the database."""

from __future__ import annotations

import datetime as dt
import json
import logging
import time
from pathlib import Path

import requests

from ..core.settings import settings
from ..services.budget import CallBudget
from ..services.coingecko import CoinGeckoClient
from ..services.dao import PricesRepo, MetaRepo, CoinsRepo
from ..services.categories import slugify
from ..db import SessionLocal

logger = logging.getLogger(__name__)
logger.setLevel(settings.log_level or "INFO")

_categories_cache: dict[str, str] = {}
_categories_cache_ts: dt.datetime | None = None


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


def run_etl(
    *,
    client: CoinGeckoClient | None = None,
    budget: CallBudget | None = None,
) -> int:
    """Fetch markets and persist them. Returns number of rows processed."""

    if client is None:
        base_url = settings.COINGECKO_BASE_URL or (
            "https://pro-api.coingecko.com/api/v3"
            if settings.COINGECKO_PLAN == "pro"
            else "https://api.coingecko.com/api/v3"
        )
        client = CoinGeckoClient(
            api_key=settings.COINGECKO_API_KEY or settings.coingecko_api_key,
            plan=settings.COINGECKO_PLAN,
            base_url=base_url,
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
            "fully_diluted_market_cap": c.get("fully_diluted_valuation"),
            "volume_24h": c.get("total_volume"),
            "rank": c.get("market_cap_rank"),
            "pct_change_24h": c.get("price_change_percentage_24h"),
            "pct_change_7d": c.get("price_change_percentage_7d_in_currency")
            or c.get("price_change_percentage_7d"),
            "pct_change_30d": c.get("price_change_percentage_30d_in_currency")
            or c.get("price_change_percentage_30d"),
            "snapshot_at": now,
        }
        for c in markets
    ]

    global _categories_cache, _categories_cache_ts
    mapping = _categories_cache
    if not _categories_cache_ts or (now - _categories_cache_ts) > dt.timedelta(
        hours=24
    ):
        try:
            cats_list = client.get_categories_list()
            calls += 1
            if budget:
                budget.spend(1)
            mapping = {slugify(c["name"]): c["category_id"] for c in cats_list}
            _categories_cache = mapping
        except Exception:  # pragma: no cover - network failures
            mapping = {}
            _categories_cache = {}
        _categories_cache_ts = now

    session = SessionLocal()
    prices_repo = PricesRepo(session)
    meta_repo = MetaRepo(session)
    coins_repo = CoinsRepo(session)

    coin_rows: list[dict] = []
    for c in markets:
        names: list[str]
        ids: list[str]
        cached_names, cached_ids, ts = coins_repo.get_categories_with_timestamp(c["id"])
        stale = ts is None or (now - ts) > dt.timedelta(hours=24)
        if stale:
            delays = [0.25, 1.0, 2.0]
            names = []
            for i in range(len(delays) + 1):
                try:
                    names = client.get_coin_categories(c["id"])
                    calls += 1
                    if budget:
                        budget.spend(1)
                    time.sleep(0.2)
                    break
                except requests.HTTPError as exc:
                    calls += 1
                    if budget:
                        budget.spend(1)
                    status = exc.response.status_code if exc.response is not None else 0
                    if status == 429 and i < len(delays):
                        time.sleep(delays[i])
                        continue
                    names = []
                    break
                except Exception:
                    names = []
                    break
            ids = [mapping.get(slugify(n), slugify(n)) for n in names]
        else:
            names, ids = cached_names, cached_ids
        coin_rows.append(
            {
                "id": c["id"],
                "symbol": c.get("symbol", ""),
                "name": c.get("name", ""),
                "category_names": json.dumps(names),
                "category_ids": json.dumps(ids),
                "updated_at": now,
            }
        )
    try:
        prices_repo.upsert_latest(price_rows)
        prices_repo.insert_snapshot(price_rows)
        coins_repo.upsert(coin_rows)
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
    logger.setLevel(settings.log_level or "INFO")
    path = Path(settings.SEED_FILE)
    if not path.exists():
        logger.warning("seed file not found at %s", path)
        logging.getLogger().warning("seed file not found at %s", path)
        return
    with path.open() as f:
        rows = json.load(f)
    now = dt.datetime.now(dt.timezone.utc)
    price_rows = [
        {
            "coin_id": r["id"],
            "vs_currency": "usd",
            "price": r.get("price"),
            "market_cap": r.get("market_cap"),
            "fully_diluted_market_cap": r.get("fully_diluted_market_cap"),
            "volume_24h": r.get("volume_24h"),
            "rank": r.get("rank"),
            "pct_change_24h": r.get("pct_change_24h"),
            "pct_change_7d": r.get("pct_change_7d"),
            "pct_change_30d": r.get("pct_change_30d"),
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
    message = json.dumps(
        {
            "event": "seed load completed",
            "seed_file": str(path),
            "rows": len(price_rows),
            "data_source": "seed",
        }
    )
    previous_level = logger.level
    try:
        logger.setLevel(logging.INFO)
        logger.info(message)
    finally:
        logger.setLevel(previous_level)
    root_logger = logging.getLogger()
    previous_root_level = root_logger.level
    try:
        root_logger.setLevel(logging.INFO)
        root_logger.info(message)
    finally:
        root_logger.setLevel(previous_root_level)
