"""FastAPI entrypoint exposing Tokenlysis endpoints and background ETL."""

from __future__ import annotations

import asyncio
from copy import deepcopy
import datetime as dt
import logging
import math
import os
import threading
import hashlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import requests
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError

from .clients.cmc_fng import (
    CoinMarketCapFearGreedClient,
    build_default_client as build_fng_client,
)
from .core.settings import effective_coingecko_base_url, mask_secret, settings
from .core.scheduling import (
    refresh_granularity_to_seconds,
    refresh_granularity_to_timedelta,
)
from .core.version import get_version
from .db import Base, engine, get_session
from .etl.historical_import import import_historical_data
from .etl.run import DataUnavailable, load_seed, run_etl
from .schemas.version import VersionResponse
from .models import FearGreed
from .services.budget import CallBudget
from .services.dao import PricesRepo, MetaRepo, CoinsRepo, FearGreedRepo
from .services.fear_greed import DEFAULT_CLASSIFICATION, sync_fear_greed_index
from .services.markets_cache import MarketsCache
from .services.serialization import serialize_price

logger = logging.getLogger(__name__)
logger.setLevel(settings.log_level or "INFO")

app = FastAPI(title="Tokenlysis", version=os.getenv("APP_VERSION", "dev"))

ETL_SHUTDOWN_TIMEOUT = 10.0
MARKETS_CACHE_TTL_SECONDS = 90
USAGE_TIMEOUT_SECONDS = 10
USAGE_CACHE_TTL_SECONDS = 90

COINGECKO_USAGE_URL = "https://pro-api.coingecko.com/api/v3/key"
COINMARKETCAP_USAGE_URL = "https://pro-api.coinmarketcap.com/v1/key/info"

app.state.markets_cache = MarketsCache(ttl_seconds=MARKETS_CACHE_TTL_SECONDS)
app.state.usage_cache: dict[str, object] | None = None


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _static_directory() -> Path:
    configured = settings.STATIC_ROOT
    if configured:
        path = Path(configured)
        if not path.is_absolute():
            return (_repo_root() / path).resolve()
        return path.expanduser().resolve()
    return (_repo_root() / "frontend").resolve()


@app.get("/info")
def info() -> dict:
    """Return build metadata so operators can verify deployed artifacts."""
    return {
        "version": os.getenv("APP_VERSION", "dev"),
        "commit": os.getenv("GIT_COMMIT", "unknown"),
        "build_time": os.getenv("BUILD_TIME", ""),
    }


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)


RANGE_TO_DELTA: dict[str, dt.timedelta] = {
    "24h": dt.timedelta(hours=24),
    "7d": dt.timedelta(days=7),
    "1m": dt.timedelta(days=30),
    "3m": dt.timedelta(days=90),
    "1y": dt.timedelta(days=365),
    "2y": dt.timedelta(days=730),
    "5y": dt.timedelta(days=1825),
}


FNG_UNAVAILABLE_DETAIL = "fear_greed_unavailable"


def get_fng_client() -> CoinMarketCapFearGreedClient:
    """Dependency factory returning the configured Fear & Greed API client."""

    return build_fng_client()


def _get_cmc_budget() -> CallBudget | None:
    return getattr(app.state, "cmc_budget", None)


def _disable_cmc_budget(exc: BaseException) -> None:
    if getattr(app.state, "cmc_budget", None) is None:
        return
    logger.warning("fear & greed budget disabled: %s", exc)
    app.state.cmc_budget = None


def _cmc_can_spend(budget: CallBudget | None, calls: int) -> bool:
    if budget is None:
        return True
    try:
        return budget.can_spend(calls)
    except Exception as exc:  # pragma: no cover - defensive
        _disable_cmc_budget(exc)
        return True


def _cmc_spend(budget: CallBudget | None, calls: int, *, category: str) -> None:
    if budget is None:
        return
    try:
        budget.spend(calls, category=category)
    except Exception as exc:  # pragma: no cover - defensive
        _disable_cmc_budget(exc)


def _safe_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return max(number, 0)


def _coingecko_usage_headers(api_key: str) -> dict[str, str]:
    header = "x-cg-pro-api-key" if settings.COINGECKO_PLAN == "pro" else "x-cg-demo-api-key"
    return {header: api_key}


def _usage_cache_signature(cg_key: str, cmc_key: str) -> str:
    digest = hashlib.sha256()
    digest.update(cg_key.encode("utf-8"))
    digest.update(b"\0")
    digest.update(cmc_key.encode("utf-8"))
    digest.update(b"\0")
    digest.update(settings.COINGECKO_PLAN.encode("utf-8"))
    return digest.hexdigest()


def _get_cached_usage(signature: str, now: dt.datetime) -> dict[str, dict[str, object]] | None:
    cache = getattr(app.state, "usage_cache", None)
    if not isinstance(cache, dict):
        return None
    cached_signature = cache.get("signature")
    expires_at = cache.get("expires_at")
    value = cache.get("value")
    if cached_signature != signature:
        return None
    if not isinstance(expires_at, dt.datetime):
        return None
    if expires_at <= now:
        return None
    if not isinstance(value, dict):
        return None
    return deepcopy(value)


def _fetch_coingecko_usage(api_key: str) -> dict[str, object]:
    headers = _coingecko_usage_headers(api_key)
    response = requests.get(COINGECKO_USAGE_URL, headers=headers, timeout=USAGE_TIMEOUT_SECONDS)
    response.raise_for_status()
    payload = response.json()
    plan = payload.get("plan") if isinstance(payload, dict) else None
    credit = _safe_int(payload.get("monthly_call_credit")) if isinstance(payload, dict) else None
    used = (
        _safe_int(payload.get("current_total_monthly_calls"))
        if isinstance(payload, dict)
        else None
    )
    remaining = (
        _safe_int(payload.get("current_remaining_monthly_calls"))
        if isinstance(payload, dict)
        else None
    )
    quota = credit if credit is not None else None
    if quota is None and used is not None and remaining is not None:
        quota = used + remaining
    return {
        "plan": plan,
        "monthly_call_credit": credit,
        "current_total_monthly_calls": used,
        "current_remaining_monthly_calls": remaining,
        "monthly_call_count": used,
        "quota": quota,
        "remaining": remaining,
    }


def _extract_monthly_usage(candidate: dict[str, object] | None) -> dict[str, int | None]:
    if not isinstance(candidate, dict):
        return {"credits_used": None, "credits_left": None, "quota": None}
    used = _safe_int(
        candidate.get("credits_used")
        or candidate.get("used")
        or candidate.get("credit_usage")
    )
    left = _safe_int(
        candidate.get("credits_left")
        or candidate.get("left")
        or candidate.get("credits_remaining")
    )
    quota = _safe_int(
        candidate.get("quota")
        or candidate.get("credit_limit")
        or candidate.get("limit")
    )
    if quota is None and used is not None and left is not None:
        quota = used + left
    if left is None and quota is not None and used is not None:
        left = max(quota - used, 0)
    return {"credits_used": used, "credits_left": left, "quota": quota}


def _fetch_cmc_usage(api_key: str) -> dict[str, object]:
    headers = {"X-CMC_PRO_API_KEY": api_key, "Accept": "application/json"}
    response = requests.get(
        COINMARKETCAP_USAGE_URL,
        headers=headers,
        timeout=USAGE_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    data = payload.get("data") if isinstance(payload, dict) else None
    plan = data.get("plan") if isinstance(data, dict) else None
    usage = data.get("usage") if isinstance(data, dict) else None
    monthly_raw = None
    if isinstance(usage, dict):
        monthly_raw = usage.get("current_month") or usage.get("monthly")
    monthly = _extract_monthly_usage(monthly_raw if isinstance(monthly_raw, dict) else None)
    quota = monthly["quota"]
    if quota is None and isinstance(plan, dict):
        quota = _safe_int(
            plan.get("credit_limit_monthly")
            or plan.get("credit_limit")
            or plan.get("quota")
        )
        monthly["quota"] = quota
        if quota is not None and monthly["credits_left"] is None and monthly["credits_used"] is not None:
            monthly["credits_left"] = max(quota - monthly["credits_used"], 0)
    used = monthly["credits_used"]
    remaining = monthly["credits_left"]
    if remaining is None and quota is not None and used is not None:
        remaining = max(quota - used, 0)
    return {
        "plan": plan,
        "usage": usage,
        "monthly": monthly,
        "monthly_call_count": used,
        "quota": quota,
        "remaining": remaining,
    }


def _parse_fng_timestamp(raw: object) -> dt.datetime | None:
    if isinstance(raw, dt.datetime):
        return raw.astimezone(dt.timezone.utc) if raw.tzinfo else raw.replace(tzinfo=dt.timezone.utc)
    if isinstance(raw, (int, float)):
        if not math.isfinite(raw):
            return None
        return dt.datetime.fromtimestamp(float(raw), tz=dt.timezone.utc)
    if isinstance(raw, str):
        candidate = raw.strip()
        if candidate:
            if candidate.endswith("Z"):
                candidate = f"{candidate[:-1]}+00:00"
            try:
                parsed = dt.datetime.fromisoformat(candidate)
            except ValueError:
                pass
            else:
                normalized = parsed.replace(tzinfo=parsed.tzinfo or dt.timezone.utc)
                return normalized.astimezone(dt.timezone.utc)
    return None


def _parse_meta_timestamp(raw: object) -> dt.datetime | None:
    if isinstance(raw, dt.datetime):
        return (
            raw.replace(tzinfo=dt.timezone.utc)
            if raw.tzinfo is None
            else raw.astimezone(dt.timezone.utc)
        )
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
                parsed = dt.datetime.strptime(candidate, "%Y-%m-%d")
            except ValueError:
                return None
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc)
    return None


def _isoformat_z(value: dt.datetime) -> str:
    normalized = value.astimezone(dt.timezone.utc)
    text = normalized.isoformat()
    if text.endswith("+00:00"):
        return text[:-6] + "Z"
    return text


def _normalize_fng_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return None
    timestamp_raw = payload.get("timestamp") or payload.get("time")
    timestamp_dt = _parse_fng_timestamp(timestamp_raw)
    if not isinstance(timestamp_dt, dt.datetime):
        return None
    score_source = payload.get("score") if "score" in payload else payload.get("value")
    try:
        score = int(round(float(score_source)))
    except (TypeError, ValueError):
        return None
    score = max(0, min(100, score))
    label_raw = (
        payload.get("label")
        or payload.get("classification")
        or payload.get("value_classification")
        or payload.get("valueClassification")
    )
    label = (str(label_raw).strip() or DEFAULT_CLASSIFICATION) if label_raw else DEFAULT_CLASSIFICATION
    return {
        "timestamp": _isoformat_z(timestamp_dt),
        "score": score,
        "label": label,
    }


def _should_refresh_fng(
    *,
    last_refresh: dt.datetime | None,
    now: dt.datetime,
    guard: dt.timedelta,
    has_cache: bool,
) -> bool:
    if not has_cache:
        return True
    if last_refresh is None:
        return True
    normalized_last = last_refresh.astimezone(dt.timezone.utc)
    if normalized_last > now:
        return True
    return (now - normalized_last) >= guard


def _serialize_fng_row(row: FearGreed | None) -> dict[str, object] | None:
    if row is None or row.timestamp is None:
        return None
    timestamp = row.timestamp
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=dt.timezone.utc)
    else:
        timestamp = timestamp.astimezone(dt.timezone.utc)
    value = row.value if row.value is not None else 0
    classification = (
        str(row.classification).strip() if row.classification is not None else ""
    ) or DEFAULT_CLASSIFICATION
    return {
        "timestamp": _isoformat_z(timestamp),
        "score": int(value),
        "label": classification,
    }


@app.get("/api/markets/top")
def markets_top(
    limit: int = 20,
    vs: str = "usd",
    session: Session = Depends(get_session),
):
    """Return market snapshots, clamp limit and raise HTTP 400 for unsupported vs."""
    vs = vs.lower()
    if vs != "usd":
        raise HTTPException(status_code=400, detail="unsupported vs")
    limit_effective = min(max(limit, 1), settings.CG_TOP_N)
    logger.debug("markets_top", extra={"limit_effective": limit_effective, "vs": vs})
    prices_repo = PricesRepo(session)
    cache: MarketsCache | None = getattr(app.state, "markets_cache", None)
    if cache is not None:
        prices_repo.get_top(vs, limit_effective)
        return cache.get_top(session, vs, limit_effective)

    meta_repo = MetaRepo(session)
    coins_repo = CoinsRepo(session)
    rows = prices_repo.get_top(vs, limit_effective)
    details_map = coins_repo.get_details_bulk([r.coin_id for r in rows])
    last_refresh_at = meta_repo.get("last_refresh_at")
    data_source = meta_repo.get("data_source")
    stale = True
    if last_refresh_at:
        try:
            ts = dt.datetime.fromisoformat(last_refresh_at)
            stale = (dt.datetime.now(dt.timezone.utc) - ts) > dt.timedelta(hours=24)
        except Exception:  # pragma: no cover - defensive
            pass
    return {
        "items": [serialize_price(r, details_map.get(r.coin_id, {})) for r in rows],
        "last_refresh_at": last_refresh_at,
        "data_source": data_source,
        "stale": stale,
    }


@app.get("/api/price/{coin_id}")
def price_detail(
    coin_id: str,
    vs: str = "usd",
    session: Session = Depends(get_session),
):
    """Return the latest snapshot for a single asset or raise 404 when missing."""
    cache: MarketsCache | None = getattr(app.state, "markets_cache", None)
    if cache is not None:
        cached = cache.get_price(session, vs, coin_id)
        if cached is None:
            raise HTTPException(status_code=404)
        return cached

    prices_repo = PricesRepo(session)
    coins_repo = CoinsRepo(session)
    row = prices_repo.get_price(coin_id, vs)
    if row is None:
        raise HTTPException(status_code=404)
    details = coins_repo.get_details(coin_id)
    return serialize_price(row, details)


@app.get("/api/price/{coin_id}/history")
def price_history(
    coin_id: str,
    range_: str = Query("7d", alias="range"),
    vs: str = "usd",
    session: Session = Depends(get_session),
):
    vs = vs.lower()
    if vs != "usd":
        raise HTTPException(status_code=400, detail="unsupported vs")
    range_key = range_.lower()
    delta = RANGE_TO_DELTA.get(range_key)
    if range_key not in RANGE_TO_DELTA and range_key != "max":
        raise HTTPException(status_code=400, detail="unsupported range")
    since = None
    if delta is not None:
        now = dt.datetime.now(dt.timezone.utc)
        since = now - delta
    prices_repo = PricesRepo(session)
    rows = prices_repo.get_history(coin_id, vs, since)
    points: list[dict] = []
    for row in rows:
        snapshot = row.snapshot_at
        if snapshot.tzinfo is None:
            snapshot = snapshot.replace(tzinfo=dt.timezone.utc)
        points.append(
            {
                "snapshot_at": snapshot.isoformat(),
                "price": row.price,
                "market_cap": row.market_cap,
                "fully_diluted_market_cap": row.fully_diluted_market_cap,
                "volume_24h": row.volume_24h,
            }
        )
    return {
        "coin_id": coin_id,
        "vs_currency": vs,
        "range": range_key,
        "points": points,
    }


@app.get("/api/coins/{coin_id}/categories")
def coin_categories(coin_id: str, session: Session = Depends(get_session)) -> dict:
    """Expose cached category names and identifiers for the requested coin."""
    coins_repo = CoinsRepo(session)
    names, ids = coins_repo.get_categories(coin_id)
    return {"category_names": names, "category_ids": ids}


@app.get("/api/fng/latest")
def fng_latest(
    client: CoinMarketCapFearGreedClient = Depends(get_fng_client),
    session: Session = Depends(get_session),
) -> dict:
    """Return the latest Fear & Greed datapoint with graceful degradation."""

    repo = FearGreedRepo(session)
    meta_repo = MetaRepo(session)
    now = dt.datetime.now(dt.timezone.utc)
    guard = refresh_granularity_to_timedelta(settings.REFRESH_GRANULARITY)
    last_refresh = _parse_meta_timestamp(meta_repo.get("fear_greed_last_refresh"))
    cached_row = repo.get_latest()
    has_cache = cached_row is not None
    should_refresh = _should_refresh_fng(
        last_refresh=last_refresh, now=now, guard=guard, has_cache=has_cache
    )

    refresh_error: Exception | None = None
    cmc_budget = _get_cmc_budget()
    if not should_refresh and has_cache:
        cached = _serialize_fng_row(cached_row)
        if cached is not None:
            return cached
        should_refresh = True

    if should_refresh:
        try:
            sync_fear_greed_index(
                session=session, client=client, now=now, budget=cmc_budget
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("fear & greed sync failed during latest fetch: %s", exc)
            refresh_error = exc

    cached = _serialize_fng_row(repo.get_latest())
    if cached is not None:
        if refresh_error is not None:
            logger.warning(
                "fear & greed latest served from stale cache after refresh failure"
            )
        elif should_refresh:
            logger.info("fear & greed latest served from refreshed cache")
        else:
            logger.info("fear & greed latest served from database cache")
        return cached

    latest_error: requests.RequestException | None = None
    latest: dict[str, object] | None = None
    if _cmc_can_spend(cmc_budget, 1):
        try:
            latest_raw = client.get_latest()
            latest = _normalize_fng_payload(latest_raw)
        except requests.RequestException as exc:
            logger.warning("fear & greed latest fetch failed: %s", exc)
            latest_error = exc
        finally:
            _cmc_spend(cmc_budget, 1, category="cmc_latest")
    elif cmc_budget is not None:
        logger.warning(
            "fear & greed latest fetch skipped: CMC quota exceeded",
            extra={
                "monthly_call_count": cmc_budget.monthly_call_count,
                "quota": settings.CMC_MONTHLY_QUOTA,
            },
        )
    if latest is not None:
        return latest

    history_error: requests.RequestException | None = None
    fallback_point: dict[str, object] | None = None
    if _cmc_can_spend(cmc_budget, 1):
        try:
            history = client.get_historical(limit=1)
        except requests.RequestException as exc:
            logger.error("fear & greed fallback fetch failed: %s", exc)
            history_error = exc
        else:
            for candidate in reversed(history or []):
                normalized = _normalize_fng_payload(candidate)
                if normalized is not None:
                    fallback_point = normalized
                    break
        finally:
            _cmc_spend(cmc_budget, 1, category="cmc_history")
    elif cmc_budget is not None:
        logger.warning(
            "fear & greed history fallback skipped: CMC quota exceeded",
            extra={
                "monthly_call_count": cmc_budget.monthly_call_count,
                "quota": settings.CMC_MONTHLY_QUOTA,
            },
        )
    if fallback_point is not None:
        return fallback_point

    detail = FNG_UNAVAILABLE_DETAIL
    if history_error is not None:
        raise HTTPException(status_code=503, detail=detail) from history_error
    if latest_error is not None:
        raise HTTPException(status_code=503, detail=detail) from latest_error
    raise HTTPException(status_code=503, detail=detail)


@app.get("/api/fng/history")
def fng_history(
    days: int | None = Query(None),
    client: CoinMarketCapFearGreedClient = Depends(get_fng_client),
    session: Session = Depends(get_session),
) -> dict:
    """Return historical Fear & Greed datapoints sorted chronologically."""

    limit: int | None = None
    if days is not None:
        try:
            limit = int(days)
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=400,
                detail="invalid days parameter",
            ) from None
        if limit <= 0:
            raise HTTPException(status_code=400, detail="days must be positive")

    repo = FearGreedRepo(session)
    meta_repo = MetaRepo(session)
    now = dt.datetime.now(dt.timezone.utc)
    guard = refresh_granularity_to_timedelta(settings.REFRESH_GRANULARITY)
    last_refresh = _parse_meta_timestamp(meta_repo.get("fear_greed_last_refresh"))
    has_cache = repo.count() > 0
    should_refresh = _should_refresh_fng(
        last_refresh=last_refresh, now=now, guard=guard, has_cache=has_cache
    )

    refresh_error: Exception | None = None
    cmc_budget = _get_cmc_budget()
    if should_refresh:
        try:
            sync_fear_greed_index(
                session=session, client=client, now=now, budget=cmc_budget
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("fear & greed sync failed during history fetch: %s", exc)
            refresh_error = exc

    rows = repo.get_history()
    if limit is not None and limit > 0:
        rows = rows[-limit:]
    cached_points = [_serialize_fng_row(row) for row in rows]
    ordered = [point for point in cached_points if point is not None]
    if ordered:
        extra = {"count": len(ordered)}
        if refresh_error is not None:
            logger.warning(
                "fear & greed history served from stale cache after refresh failure",
                extra=extra,
            )
        elif should_refresh:
            logger.info(
                "fear & greed history served from refreshed cache",
                extra=extra,
            )
        else:
            logger.info(
                "fear & greed history served from database cache",
                extra=extra,
            )
        return {"days": limit, "points": ordered}

    fetch_error: requests.RequestException | None = None
    normalized_points: list[dict[str, object]] = []
    if _cmc_can_spend(cmc_budget, 1):
        try:
            points = client.get_historical(limit=limit)
        except requests.RequestException as exc:
            logger.error("fear & greed history fetch failed: %s", exc)
            fetch_error = exc
        else:
            for raw_point in points or []:
                normalized = _normalize_fng_payload(raw_point)
                if normalized is not None:
                    normalized_points.append(normalized)
        finally:
            _cmc_spend(cmc_budget, 1, category="cmc_history")
    elif cmc_budget is not None:
        logger.warning(
            "fear & greed history fetch skipped: CMC quota exceeded",
            extra={
                "monthly_call_count": cmc_budget.monthly_call_count,
                "quota": settings.CMC_MONTHLY_QUOTA,
            },
        )
    if normalized_points:
        ordered = sorted(
            normalized_points,
            key=lambda item: _parse_fng_timestamp(item.get("timestamp"))
            or dt.datetime.min.replace(tzinfo=dt.timezone.utc),
        )
        if ordered:
            return {"days": limit, "points": ordered}
    if fetch_error is not None:
        raise HTTPException(
            status_code=503,
            detail=FNG_UNAVAILABLE_DETAIL,
        ) from fetch_error
    return {"days": limit, "points": []}


@app.get("/api/debug/history-gaps")
def history_gaps(session: Session = Depends(get_session)) -> dict:
    """Report coins with missing historical points for diagnostic purposes."""

    prices_repo = PricesRepo(session)
    vs_currency = "usd"
    limit = max(int(settings.CG_TOP_N), 0)
    latest_rows = prices_repo.get_top(vs_currency, limit) if limit else []
    now = dt.datetime.now(dt.timezone.utc)
    granularity_seconds = max(refresh_interval_seconds(settings.REFRESH_GRANULARITY), 1)
    items: list[dict[str, object]] = []

    for row in latest_rows:
        missing_ranges: dict[str, dict[str, int]] = {}
        coin_vs = row.vs_currency
        for range_key, delta in RANGE_TO_DELTA.items():
            seconds = delta.total_seconds()
            if seconds <= 0:
                continue
            expected = max(int(math.ceil(seconds / granularity_seconds)), 1)
            since = now - delta
            history = prices_repo.get_history(row.coin_id, coin_vs, since)
            actual = len(history)
            missing = max(expected - actual, 0)
            if missing > 0:
                missing_ranges[range_key] = {
                    "expected": expected,
                    "actual": actual,
                    "missing": missing,
                }
        if missing_ranges:
            items.append({"coin_id": row.coin_id, "ranges": missing_ranges})

    return {
        "generated_at": now.isoformat(),
        "granularity": settings.REFRESH_GRANULARITY,
        "vs_currency": vs_currency,
        "items": items,
    }


@app.get("/api/debug/categories")
def debug_categories(session: Session = Depends(get_session)) -> dict:
    """Report coins with missing category data for diagnostic purposes."""

    coins_repo = CoinsRepo(session)
    now = dt.datetime.now(dt.timezone.utc)
    stale_after = dt.timedelta(hours=24)
    issues = coins_repo.list_category_issues(now=now, stale_after=stale_after)

    def _format_timestamp(value: dt.datetime | None) -> str | None:
        if value is None:
            return None
        return value.astimezone(dt.timezone.utc).isoformat()

    items: list[dict[str, object]] = []
    for issue in issues:
        items.append(
            {
                "coin_id": issue["coin_id"],
                "category_names": list(issue.get("category_names", [])),
                "updated_at": _format_timestamp(issue.get("updated_at")),
                "reasons": list(issue.get("reasons", [])),
            }
        )

    hours = stale_after.total_seconds() / (60 * 60)
    stale_after_hours = hours if hours.is_integer() else round(hours, 2)

    return {
        "generated_at": now.isoformat(),
        "stale_after_hours": (
            int(stale_after_hours)
            if isinstance(stale_after_hours, float) and stale_after_hours.is_integer()
            else stale_after_hours
        ),
        "items": items,
    }


@app.get("/api/diag")
def diag(session: Session = Depends(get_session)) -> dict:
    """Expose runtime diagnostics including call budget and ETL metadata."""
    meta_repo = MetaRepo(session)
    last_refresh_at = meta_repo.get("last_refresh_at")
    last_etl_items_raw = meta_repo.get("last_etl_items")
    data_source = meta_repo.get("data_source")
    fear_greed_last_refresh = meta_repo.get("fear_greed_last_refresh")
    fear_greed_repo = FearGreedRepo(session)
    try:
        if last_etl_items_raw is None:
            last_etl_items = 0
        else:
            last_etl_items = int(last_etl_items_raw)
    except Exception:  # pragma: no cover - defensive
        last_etl_items = 0
    budget: CallBudget | None = getattr(app.state, "budget", None)
    monthly_call_count = budget.monthly_call_count if budget else 0
    monthly_call_categories = budget.category_counts if budget else {}
    cmc_budget = _get_cmc_budget()
    cmc_monthly_call_count = cmc_budget.monthly_call_count if cmc_budget else 0
    cmc_monthly_call_categories = cmc_budget.category_counts if cmc_budget else {}
    fear_greed_count = fear_greed_repo.count()

    parsed_last_refresh = _parse_meta_timestamp(last_refresh_at)
    parsed_fng_last_refresh = _parse_meta_timestamp(fear_greed_last_refresh)
    earliest_ts, latest_ts = fear_greed_repo.get_timespan()

    fng_cache = {
        "rows": fear_greed_count,
        "last_refresh": _isoformat_z(parsed_fng_last_refresh)
        if isinstance(parsed_fng_last_refresh, dt.datetime)
        else None,
        "min_timestamp": _isoformat_z(earliest_ts) if isinstance(earliest_ts, dt.datetime) else None,
        "max_timestamp": _isoformat_z(latest_ts) if isinstance(latest_ts, dt.datetime) else None,
    }

    cg_base_url = effective_coingecko_base_url().rstrip("/")
    cmc_base_url = (settings.CMC_BASE_URL or "https://pro-api.coinmarketcap.com").rstrip("/")
    cg_key_raw = settings.COINGECKO_API_KEY or settings.coingecko_api_key

    providers = {
        "coinmarketcap": {
            "base_url": cmc_base_url,
            "api_key_masked": mask_secret(settings.CMC_API_KEY),
            "fng_latest": {
                "path": "/v3/fear-and-greed/latest",
                "doc_url": "https://coinmarketcap.com/api/documentation/v3/#operation/getV3FearAndGreedLatest",
                "safe_url": f"{cmc_base_url}/v3/fear-and-greed/latest",
            },
            "fng_historical": {
                "path": "/v3/fear-and-greed/historical",
                "doc_url": "https://coinmarketcap.com/api/documentation/v3/#operation/getV3FearAndGreedHistorical",
                "safe_url": f"{cmc_base_url}/v3/fear-and-greed/historical",
            },
        },
        "coingecko": {
            "base_url": cg_base_url,
            "api_key_masked": mask_secret(cg_key_raw),
            "markets": {
                "path": "/coins/markets",
                "doc_url": "https://www.coingecko.com/en/api/documentation",
                "safe_url": f"{cg_base_url}/coins/markets?vs_currency=usd",
            },
        },
    }

    etl = {
        "granularity": settings.REFRESH_GRANULARITY,
        "last_refresh_at": _isoformat_z(parsed_last_refresh)
        if isinstance(parsed_last_refresh, dt.datetime)
        else None,
        "last_etl_items": last_etl_items,
        "top_n": settings.CG_TOP_N,
        "data_source": data_source,
    }

    coingecko_usage = {
        "plan": settings.COINGECKO_PLAN,
        "monthly_call_count": monthly_call_count,
        "monthly_call_categories": monthly_call_categories,
        "quota": settings.CG_MONTHLY_QUOTA,
    }

    coinmarketcap_usage = {
        "monthly_call_count": cmc_monthly_call_count,
        "monthly_call_categories": cmc_monthly_call_categories,
        "quota": settings.CMC_MONTHLY_QUOTA,
        "alert_threshold": settings.CMC_ALERT_THRESHOLD,
    }

    response = {
        "providers": providers,
        "etl": etl,
        "coingecko_usage": coingecko_usage,
        "coinmarketcap_usage": coinmarketcap_usage,
        "fng_cache": fng_cache,
        # legacy fields for compatibility
        "plan": coingecko_usage["plan"],
        "base_url": cg_base_url,
        "granularity": etl["granularity"],
        "last_refresh_at": etl["last_refresh_at"],
        "last_etl_items": etl["last_etl_items"],
        "monthly_call_count": coingecko_usage["monthly_call_count"],
        "monthly_call_categories": coingecko_usage["monthly_call_categories"],
        "quota": coingecko_usage["quota"],
        "data_source": data_source,
        "top_n": settings.CG_TOP_N,
        "fear_greed_last_refresh": fng_cache["last_refresh"],
        "fear_greed_count": fng_cache["rows"],
        "cmc_monthly_call_count": coinmarketcap_usage["monthly_call_count"],
        "cmc_monthly_call_categories": coinmarketcap_usage["monthly_call_categories"],
        "cmc_quota": coinmarketcap_usage["quota"],
        "cmc_alert_threshold": coinmarketcap_usage["alert_threshold"],
    }

    return response


def _format_missing_keys(missing: list[str]) -> str:
    if not missing:
        return ""
    if len(missing) == 1:
        return f"La clé API {missing[0]} est requise pour actualiser les crédits."
    joined = " et ".join(missing)
    return f"Les clés API {joined} sont requises pour actualiser les crédits."


@app.post("/api/diag/refresh-usage")
def refresh_usage() -> dict[str, dict[str, object]]:
    cg_key = settings.COINGECKO_API_KEY or settings.coingecko_api_key
    cmc_key = settings.CMC_API_KEY
    missing = []
    if not cg_key:
        missing.append("CoinGecko")
    if not cmc_key:
        missing.append("CoinMarketCap")
    if missing:
        raise HTTPException(status_code=400, detail=_format_missing_keys(missing))

    now = dt.datetime.now(dt.timezone.utc)
    signature = _usage_cache_signature(str(cg_key), str(cmc_key))
    cached = _get_cached_usage(signature, now)
    if cached is not None:
        return cached

    try:
        cg_usage = _fetch_coingecko_usage(cg_key)
    except requests.RequestException as exc:  # pragma: no cover - network error
        logger.error("CoinGecko usage refresh failed: %s", exc)
        app.state.usage_cache = None
        raise HTTPException(
            status_code=502,
            detail="Échec de la récupération des crédits CoinGecko.",
        ) from exc

    try:
        cmc_usage = _fetch_cmc_usage(cmc_key)
    except requests.RequestException as exc:  # pragma: no cover - network error
        logger.error("CoinMarketCap usage refresh failed: %s", exc)
        app.state.usage_cache = None
        raise HTTPException(
            status_code=502,
            detail="Échec de la récupération des crédits CoinMarketCap.",
        ) from exc

    result = {
        "coingecko": cg_usage,
        "coinmarketcap": cmc_usage,
    }

    expires_at = now + dt.timedelta(seconds=USAGE_CACHE_TTL_SECONDS)
    app.state.usage_cache = {
        "signature": signature,
        "expires_at": expires_at,
        "value": deepcopy(result),
    }

    return result


@app.get("/api/last-refresh")
def last_refresh(session: Session = Depends(get_session)) -> dict:
    """Return the last ETL refresh timestamp for lightweight polling."""
    meta_repo = MetaRepo(session)
    last_refresh_at = meta_repo.get("last_refresh_at")
    return {"last_refresh_at": last_refresh_at}


def refresh_interval_seconds(value: str | None = None) -> int:
    """Convert refresh granularity hints to seconds with a 12h fallback."""
    return refresh_granularity_to_seconds(value, default=settings.REFRESH_GRANULARITY)


async def run_etl_async(*, budget: CallBudget | None) -> int:
    """Execute the ETL in a daemonised worker thread and refresh budget counters."""

    if budget is not None:
        budget.reset_if_needed()

    loop = asyncio.get_running_loop()
    future: asyncio.Future[int] = loop.create_future()

    def _set_result(value: int) -> None:
        if not future.done():
            future.set_result(value)

    def _set_exception(exc: BaseException) -> None:
        if not future.done():
            future.set_exception(exc)

    def _worker() -> None:
        try:
            markets_cache = getattr(app.state, "markets_cache", None)
            result = run_etl(budget=budget, markets_cache=markets_cache)
        except BaseException as exc:  # pragma: no cover - defensive
            loop.call_soon_threadsafe(_set_exception, exc)
        else:
            loop.call_soon_threadsafe(_set_result, result)

    threading.Thread(target=_worker, name="etl-worker", daemon=True).start()

    try:
        result = await future
    except asyncio.CancelledError:
        if not future.done():
            future.cancel()
        raise

    if budget is not None:
        budget.reset_if_needed()
    return result


async def sync_fear_greed_async() -> int:
    """Synchronise the Fear & Greed index without blocking the event loop."""

    budget = _get_cmc_budget()
    return await asyncio.to_thread(sync_fear_greed_index, budget=budget)


async def etl_loop(stop_event: asyncio.Event) -> None:
    """Run the ETL periodically until ``stop_event`` is set.

    The loop retries indefinitely: failures are logged, then the worker sleeps
    for :func:`refresh_interval_seconds` before trying again.
    """

    budget: CallBudget | None = getattr(app.state, "budget", None)
    try:
        while not stop_event.is_set():
            try:
                await run_etl_async(budget=budget)
            except DataUnavailable as exc:  # pragma: no cover - network failures
                logger.warning("ETL skipped: %s", exc)
            except OperationalError as exc:
                logger.warning("ETL failed: schema out-of-date: %s", exc)
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.exception("ETL failed unexpectedly: %s", exc)
            interval = refresh_interval_seconds()
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval)
            except asyncio.TimeoutError:
                continue
    except asyncio.CancelledError:
        stop_event.set()
        raise


@app.get("/healthz")
def healthz(session: Session = Depends(get_session)) -> dict:
    """Return database connectivity and bootstrap status for liveness probes."""
    db_connected = True
    try:
        session.execute(text("SELECT 1"))
    except Exception:  # pragma: no cover - defensive
        db_connected = False

    bootstrap_done = False
    last_refresh_at: str | None = None
    if db_connected:
        meta_repo = MetaRepo(session)
        last_refresh_at = meta_repo.get("last_refresh_at")
        bootstrap_done = meta_repo.get("bootstrap_done") == "true"
    return {
        "db_connected": db_connected,
        "bootstrap_done": bootstrap_done,
        "last_refresh_at": last_refresh_at,
    }


@app.get("/readyz")
def readyz(session: Session = Depends(get_session)) -> dict:
    """Report readiness by issuing a lightweight database query."""
    try:
        session.execute(text("SELECT 1"))
    except Exception:  # pragma: no cover - defensive
        raise HTTPException(status_code=503)
    return {"ready": True}


@app.get("/version", response_model=VersionResponse)
@app.get("/api/version", response_model=VersionResponse, include_in_schema=False)
def version() -> VersionResponse:
    """Expose the application version sourced from Git metadata or APP_VERSION."""
    return VersionResponse(version=get_version())


async def startup() -> None:
    """Configure logging, bootstrap persistence, run initial ETL and spawn the loop."""
    logging.basicConfig(
        level=settings.log_level or "INFO",
        format="%(message)s",
        force=True,
    )
    logger.setLevel(settings.log_level or "INFO")
    logger.info("startup", extra={"version": get_version()})
    Base.metadata.create_all(bind=engine)
    budget = None
    if settings.BUDGET_FILE:
        path = Path(settings.BUDGET_FILE)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch(exist_ok=True)
            budget = CallBudget(path, settings.CG_MONTHLY_QUOTA)
        except OSError as exc:
            logger.warning("budget file unavailable at %s: %s", path, exc)
            logging.getLogger().warning("budget file unavailable at %s: %s", path, exc)
            budget = None
    app.state.budget = budget

    cmc_budget = None
    cmc_budget_path = settings.CMC_BUDGET_FILE
    if cmc_budget_path and settings.CMC_MONTHLY_QUOTA > 0:
        cmc_path = Path(cmc_budget_path)
        try:
            cmc_path.parent.mkdir(parents=True, exist_ok=True)
            cmc_path.touch(exist_ok=True)
            cmc_budget = CallBudget(cmc_path, settings.CMC_MONTHLY_QUOTA)
        except OSError as exc:
            logger.warning("CMC budget file unavailable at %s: %s", cmc_path, exc)
            logging.getLogger().warning(
                "CMC budget file unavailable at %s: %s", cmc_path, exc
            )
            cmc_budget = None
    app.state.cmc_budget = cmc_budget

    session = next(get_session())
    meta_repo = MetaRepo(session)
    prices_repo = PricesRepo(session)
    path_taken = "skip"
    should_run_historical_import = False
    historical_import_done = meta_repo.get("historical_import_done") == "true"
    has_data = False
    try:
        if meta_repo.get("bootstrap_done") != "true":
            try:
                await run_etl_async(budget=budget)
            except DataUnavailable:
                if settings.use_seed_on_failure:
                    load_seed()
                    path_taken = "seed"
                    should_run_historical_import = True
            except OperationalError as exc:
                logger.warning("startup ETL failed: %s", exc)
                if settings.use_seed_on_failure:
                    load_seed()
                    path_taken = "seed"
                    should_run_historical_import = True
            else:
                path_taken = "ETL"
                should_run_historical_import = True
            meta_repo.set("bootstrap_done", "true")
        else:
            has_data = bool(prices_repo.get_top("usd", 1))
            if not has_data:
                try:
                    await run_etl_async(budget=budget)
                except DataUnavailable:
                    if settings.use_seed_on_failure:
                        load_seed()
                        path_taken = "seed"
                        should_run_historical_import = True
                except OperationalError as exc:
                    logger.warning("startup ETL failed: %s", exc)
                    if settings.use_seed_on_failure:
                        load_seed()
                        path_taken = "seed"
                        should_run_historical_import = True
                else:
                    path_taken = "ETL"
                    should_run_historical_import = True
        if not should_run_historical_import and not historical_import_done and has_data:
            should_run_historical_import = True
        session.commit()
    finally:
        session.close()

    if should_run_historical_import:
        session = next(get_session())
        try:
            meta_repo = MetaRepo(session)
            meta_repo.set("historical_import_done", "false")
            session.commit()
            import_historical_data(session)
            meta_repo.set("historical_import_done", "true")
            session.commit()
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("historical import skipped: %s", exc)
            session.rollback()
        finally:
            session.close()

    try:
        await sync_fear_greed_async()
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("startup fear & greed sync skipped: %s", exc)

    logger.debug("startup path: %s", path_taken)
    app.state.startup_path = path_taken
    stop_event = asyncio.Event()
    app.state.etl_stop_event = stop_event
    task = asyncio.create_task(etl_loop(stop_event))
    app.state.etl_task = task if isinstance(task, asyncio.Task) else None


async def shutdown() -> None:
    """Signal the ETL loop to stop without hanging on slow iterations."""

    stop_event: asyncio.Event | None = getattr(app.state, "etl_stop_event", None)
    task = getattr(app.state, "etl_task", None)
    if stop_event is not None:
        stop_event.set()
        app.state.etl_stop_event = None
    if isinstance(task, asyncio.Task):
        raw_timeout = getattr(app.state, "etl_shutdown_timeout", None)
        if isinstance(raw_timeout, (int, float)) and raw_timeout > 0:
            timeout = float(raw_timeout)
        else:
            timeout = ETL_SHUTDOWN_TIMEOUT
        if not task.done():
            task.cancel()
        try:
            await asyncio.wait_for(task, timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning(
                "ETL loop still running after %.1fs shutdown grace period; continuing",
                timeout,
            )

            def _drain_task_result(completed: asyncio.Task) -> None:
                try:
                    completed.result()
                except asyncio.CancelledError:  # pragma: no cover - defensive
                    pass
                except Exception as exc:  # pragma: no cover - defensive
                    logger.warning("ETL loop raised after shutdown: %s", exc)

            if not task.done():
                task.add_done_callback(_drain_task_result)
        except asyncio.CancelledError:  # pragma: no cover - defensive
            pass
        except Exception:  # pragma: no cover - defensive
            logger.exception("ETL loop raised during shutdown")
        finally:
            app.state.etl_task = None


STATIC_DIRECTORY = _static_directory()

app.mount("/", StaticFiles(directory=str(STATIC_DIRECTORY), html=True), name="static")


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    await startup()
    try:
        yield
    finally:
        await shutdown()


app.router.lifespan_context = _lifespan


__all__ = [
    "app",
    "etl_loop",
    "refresh_interval_seconds",
    "run_etl_async",
    "sync_fear_greed_async",
]
