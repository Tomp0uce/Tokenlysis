"""Fetch market data from CoinGecko and persist into the database."""

from __future__ import annotations

import datetime as dt
import json
import logging
import time
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING

import requests

from ..core.scheduling import refresh_granularity_to_timedelta
from ..core.settings import settings
from ..services.budget import CallBudget
from ..services.coingecko import CoinGeckoClient
from ..services.dao import PricesRepo, MetaRepo, CoinsRepo
from ..services.fear_greed import sync_fear_greed_index
from ..services.categories import slugify
from ..db import SessionLocal

if TYPE_CHECKING:
    from ..services.markets_cache import MarketsCache

logger = logging.getLogger(__name__)
logger.setLevel(settings.log_level or "INFO")

_categories_cache: dict[str, str] = {}
_categories_cache_ts: dt.datetime | None = None

_PROFILE_STALE_AFTER = dt.timedelta(days=30)


def _resolve_main_module(candidate: ModuleType | None = None) -> ModuleType | None:
    if candidate is not None:
        return candidate
    try:
        from .. import main as main_module  # type: ignore
    except Exception:  # pragma: no cover - defensive
        return None
    return main_module


def _get_cmc_budget(candidate: ModuleType | None = None) -> CallBudget | None:
    main_module = _resolve_main_module(candidate)
    if main_module is None:
        return None
    return getattr(main_module.app.state, "cmc_budget", None)


def _sync_fear_greed_with_budget(budget: CallBudget | None) -> int:
    try:
        return sync_fear_greed_index(budget=budget)
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.warning("fear & greed sync skipped: %s", exc)
        return 0


class DataUnavailable(Exception):
    """Raised when live data could not be fetched."""


def _parse_iso_timestamp(raw: str | None) -> dt.datetime | None:
    if not raw:
        return None
    candidate = raw.strip()
    if not candidate:
        return None
    try:
        parsed = dt.datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _extract_market_categories(payload: dict[str, object]) -> list[str]:
    raw = payload.get("categories")
    if not isinstance(raw, list):
        return []
    categories: list[str] = []
    for value in raw:
        if isinstance(value, str):
            cleaned = value.strip()
            if cleaned:
                categories.append(cleaned)
    return categories


def _extract_market_links(payload: dict[str, object]) -> dict[str, str]:
    raw = payload.get("links")
    if not isinstance(raw, dict):
        return {}
    links: dict[str, str] = {}
    for key, value in raw.items():
        if isinstance(key, str) and isinstance(value, str):
            cleaned = value.strip()
            if cleaned:
                links[key] = cleaned
    return links


def _fetch_markets(
    client: CoinGeckoClient,
    limit: int,
    per_page_max: int,
    budget: CallBudget | None,
) -> tuple[list[dict], int]:
    """Fetch market pages until the limit is reached while tracking API calls."""
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
                budget.spend(1, category="markets")
            status = exc.response.status_code if exc.response is not None else 0
            if 400 <= status < 500 and per_page > 100:
                per_page = 100
                continue
            raise
        calls += 1
        if budget:
            budget.spend(1, category="markets")
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
    markets_cache: "MarketsCache | None" = None,
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

    session = SessionLocal()
    try:
        prices_repo = PricesRepo(session)
        meta_repo = MetaRepo(session)
        coins_repo = CoinsRepo(session)

        guard_interval = refresh_granularity_to_timedelta(settings.REFRESH_GRANULARITY)
        interval_seconds = max(int(guard_interval.total_seconds()), 1)
        guard_now = dt.datetime.now(dt.timezone.utc)
        last_refresh = _parse_iso_timestamp(meta_repo.get("last_refresh_at"))
        has_prices = bool(prices_repo.get_top("usd", 1))
        if (
            has_prices
            and last_refresh is not None
            and (guard_now - last_refresh) < guard_interval
        ):
            logger.info(
                json.dumps(
                    {
                        "event": "etl skipped",
                        "reason": "refresh cadence not reached",
                        "last_refresh_at": last_refresh.isoformat(),
                        "interval_seconds": interval_seconds,
                    }
                )
            )
            main_module_ref = _resolve_main_module()
            _sync_fear_greed_with_budget(_get_cmc_budget(main_module_ref))
            return 0

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
                    budget.spend(1, category="categories_list")
                mapping = {slugify(c["name"]): c["category_id"] for c in cats_list}
                _categories_cache = mapping
            except Exception:  # pragma: no cover - network failures
                mapping = {}
                _categories_cache = {}
            _categories_cache_ts = now

        coin_rows: list[dict] = []
        for c in markets:
            names: list[str]
            ids: list[str]
            links: dict[str, str]
            cached_names, cached_ids, cached_links_raw, ts = (
                coins_repo.get_categories_with_timestamp(c["id"])
            )
            cached_links = (
                cached_links_raw if isinstance(cached_links_raw, dict) else {}
            )
            stale = ts is None or (now - ts) > _PROFILE_STALE_AFTER
            missing_links = not cached_links
            market_categories = _extract_market_categories(c)
            market_links = _extract_market_links(c)
            if market_categories:
                names = market_categories
                ids = [mapping.get(slugify(n), slugify(n)) for n in market_categories]
            else:
                names, ids = cached_names, cached_ids
            if market_links:
                links = dict(market_links)
            else:
                links = dict(cached_links)
            fetched_profile = False
            need_categories = not market_categories and stale
            need_links = not market_links and (missing_links or stale)
            if need_categories or need_links:
                delays = [0.25, 1.0, 2.0]
                profile: dict[str, object] = {"categories": [], "links": {}}
                for i in range(len(delays) + 1):
                    try:
                        profile = client.get_coin_profile(c["id"])
                        fetched_profile = True
                        calls += 1
                        if budget:
                            budget.spend(1, category="coin_profile")
                        time.sleep(0.2)
                        break
                    except requests.HTTPError as exc:
                        calls += 1
                        if budget:
                            budget.spend(1, category="coin_profile")
                        status = (
                            exc.response.status_code if exc.response is not None else 0
                        )
                        if status == 429 and i < len(delays):
                            time.sleep(delays[i])
                            continue
                        profile = {"categories": [], "links": {}}
                        break
                    except Exception:
                        profile = {"categories": [], "links": {}}
                        break
                categories_raw = profile.get("categories")
                names = (
                    [n for n in categories_raw if isinstance(n, str)]
                    if isinstance(categories_raw, list)
                    else []
                )
                ids = [mapping.get(slugify(n), slugify(n)) for n in names]
                links_obj = profile.get("links")
                links = links_obj if isinstance(links_obj, dict) else {}
                if not fetched_profile:
                    names, ids = cached_names, cached_ids
                    links = dict(cached_links)
                elif not links:
                    links = {"__synced__": True}
            coin_rows.append(
                {
                    "id": c["id"],
                    "symbol": c.get("symbol", ""),
                    "name": c.get("name", ""),
                    "logo_url": c.get("image"),
                    "category_names": json.dumps(names),
                    "category_ids": json.dumps(ids),
                    "social_links": json.dumps(links),
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

    cache = markets_cache
    main_module_ref: ModuleType | None = None
    if cache is None:
        main_module_ref = _resolve_main_module()
        if main_module_ref is not None:
            cache = getattr(main_module_ref.app.state, "markets_cache", None)
    if cache is not None:
        try:
            cache.invalidate()
        except Exception:  # pragma: no cover - defensive
            logger.warning("markets cache invalidation failed", exc_info=True)

    cmc_budget = _get_cmc_budget(main_module_ref)
    fear_greed_rows = _sync_fear_greed_with_budget(cmc_budget)

    logger.info(
        json.dumps(
            {
                "event": "etl run completed",
                "coingecko_calls_total": calls,
                "monthly_call_count": budget.monthly_call_count if budget else None,
                "last_refresh_at": now.isoformat(),
                "rows": len(price_rows),
                "fear_greed_rows": fear_greed_rows,
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
