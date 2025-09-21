from __future__ import annotations

"""FastAPI entrypoint exposing Tokenlysis endpoints and background ETL."""

import asyncio
import datetime as dt
import logging
import os
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError

from .core.settings import effective_coingecko_base_url, settings
from .core.version import get_version
from .db import Base, engine, get_session
from .etl.run import DataUnavailable, load_seed, run_etl
from .schemas.version import VersionResponse
from .services.budget import CallBudget
from .services.dao import PricesRepo, MetaRepo, CoinsRepo, FearGreedRepo
from .services.fear_greed import sync_fear_greed_index

logger = logging.getLogger(__name__)
logger.setLevel(settings.log_level or "INFO")

app = FastAPI(title="Tokenlysis", version=os.getenv("APP_VERSION", "dev"))


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

FEAR_GREED_RANGE_TO_DELTA: dict[str, dt.timedelta] = {
    "30d": dt.timedelta(days=30),
    "90d": dt.timedelta(days=90),
    "1y": dt.timedelta(days=365),
}


def _serialize_price(p, details: dict[str, object]) -> dict:
    """Convert ORM rows and metadata into an API payload."""
    names_raw = details.get("category_names") if details else []
    ids_raw = details.get("category_ids") if details else []
    names = list(names_raw) if isinstance(names_raw, (list, tuple)) else []
    ids = list(ids_raw) if isinstance(ids_raw, (list, tuple)) else []
    raw_name = details.get("name") if details else ""
    name = raw_name.strip() if isinstance(raw_name, str) else ""
    raw_symbol = details.get("symbol") if details else ""
    symbol = raw_symbol.strip() if isinstance(raw_symbol, str) else ""
    raw_logo = details.get("logo_url") if details else None
    logo_url = raw_logo.strip() if isinstance(raw_logo, str) and raw_logo.strip() else None
    return {
        "coin_id": p.coin_id,
        "vs_currency": p.vs_currency,
        "price": p.price,
        "market_cap": p.market_cap,
        "fully_diluted_market_cap": p.fully_diluted_market_cap,
        "volume_24h": p.volume_24h,
        "rank": p.rank,
        "pct_change_24h": p.pct_change_24h,
        "pct_change_7d": p.pct_change_7d,
        "pct_change_30d": p.pct_change_30d,
        "snapshot_at": p.snapshot_at,
        "category_names": names,
        "category_ids": ids,
        "name": name,
        "symbol": symbol,
        "logo_url": logo_url,
    }


@app.get("/api/markets/top")
def markets_top(
    limit: int = 20,
    vs: str = "usd",
    session: Session = Depends(get_session),
):
    """Return the top market snapshots, clamp the limit and emit HTTP 400 for unsupported vs."""
    vs = vs.lower()
    if vs != "usd":
        raise HTTPException(status_code=400, detail="unsupported vs")
    limit_effective = min(max(limit, 1), settings.CG_TOP_N)
    logger.info("markets_top", extra={"limit_effective": limit_effective, "vs": vs})
    prices_repo = PricesRepo(session)
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
        "items": [
            _serialize_price(r, details_map.get(r.coin_id, {})) for r in rows
        ],
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
    prices_repo = PricesRepo(session)
    coins_repo = CoinsRepo(session)
    row = prices_repo.get_price(coin_id, vs)
    if row is None:
        raise HTTPException(status_code=404)
    details = coins_repo.get_details(coin_id)
    return _serialize_price(row, details)


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


@app.get("/api/fear-greed/latest")
def fear_greed_latest(session: Session = Depends(get_session)) -> dict:
    """Return the most recent Crypto Fear & Greed datapoint."""

    repo = FearGreedRepo(session)
    row = repo.get_latest()
    if row is None:
        raise HTTPException(status_code=404)
    timestamp = row.timestamp
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=dt.timezone.utc)
    else:
        timestamp = timestamp.astimezone(dt.timezone.utc)
    return {
        "timestamp": timestamp.isoformat(),
        "value": row.value,
        "classification": row.classification,
    }


@app.get("/api/fear-greed/history")
def fear_greed_history(
    range_: str = Query("90d", alias="range"),
    session: Session = Depends(get_session),
) -> dict:
    """Return historical values for the Crypto Fear & Greed index."""

    range_key = (range_ or "max").lower()
    if range_key != "max" and range_key not in FEAR_GREED_RANGE_TO_DELTA:
        raise HTTPException(status_code=400, detail="unsupported range")
    since: dt.datetime | None = None
    if range_key != "max":
        delta = FEAR_GREED_RANGE_TO_DELTA[range_key]
        since = dt.datetime.now(dt.timezone.utc) - delta
    repo = FearGreedRepo(session)
    rows = repo.get_history(since)
    points: list[dict] = []
    for row in rows:
        timestamp = row.timestamp
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=dt.timezone.utc)
        else:
            timestamp = timestamp.astimezone(dt.timezone.utc)
        points.append(
            {
                "timestamp": timestamp.isoformat(),
                "value": row.value,
                "classification": row.classification,
            }
        )
    return {"range": range_key, "points": points}


@app.get("/api/diag")
def diag(session: Session = Depends(get_session)) -> dict:
    """Expose runtime diagnostics including call budget and ETL metadata."""
    meta_repo = MetaRepo(session)
    last_refresh_at = meta_repo.get("last_refresh_at")
    last_etl_items_raw = meta_repo.get("last_etl_items")
    data_source = meta_repo.get("data_source")
    try:
        if last_etl_items_raw is None:
            last_etl_items = 0
        else:
            last_etl_items = int(last_etl_items_raw)
    except Exception:  # pragma: no cover - defensive
        last_etl_items = 0
    budget: CallBudget | None = getattr(app.state, "budget", None)
    monthly_call_count = budget.monthly_call_count if budget else 0
    return {
        "plan": settings.COINGECKO_PLAN,
        "base_url": effective_coingecko_base_url(),
        "granularity": settings.REFRESH_GRANULARITY,
        "last_refresh_at": last_refresh_at,
        "last_etl_items": last_etl_items,
        "monthly_call_count": monthly_call_count,
        "quota": settings.CG_MONTHLY_QUOTA,
        "data_source": data_source,
        "top_n": settings.CG_TOP_N,
    }


@app.get("/api/last-refresh")
def last_refresh(session: Session = Depends(get_session)) -> dict:
    """Return the last ETL refresh timestamp for lightweight polling."""
    meta_repo = MetaRepo(session)
    last_refresh_at = meta_repo.get("last_refresh_at")
    return {"last_refresh_at": last_refresh_at}


def refresh_interval_seconds(value: str | None = None) -> int:
    """Convert refresh granularity hints to seconds with a 12h fallback."""
    granularity = value or settings.REFRESH_GRANULARITY
    try:
        if granularity.endswith("h"):
            return int(float(granularity[:-1]) * 60 * 60)
    except Exception:  # pragma: no cover - defensive
        pass
    return 12 * 60 * 60


async def etl_loop() -> None:
    """Background loop triggering the ETL and tolerating transient failures."""
    while True:
        try:
            run_etl(budget=app.state.budget)
        except DataUnavailable as exc:  # pragma: no cover - network failures
            logger.warning("ETL skipped: %s", exc)
        except OperationalError as exc:
            logger.warning("ETL failed: schema out-of-date: %s", exc)
        await asyncio.sleep(refresh_interval_seconds())


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


@app.on_event("startup")
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

    session = next(get_session())
    meta_repo = MetaRepo(session)
    prices_repo = PricesRepo(session)
    path_taken = "skip"
    try:
        if meta_repo.get("bootstrap_done") != "true":
            try:
                run_etl(budget=budget)
                path_taken = "ETL"
            except DataUnavailable:
                if settings.use_seed_on_failure:
                    load_seed()
                    path_taken = "seed"
            except OperationalError as exc:
                logger.warning("startup ETL failed: %s", exc)
                if settings.use_seed_on_failure:
                    load_seed()
                    path_taken = "seed"
            meta_repo.set("bootstrap_done", "true")
        else:
            has_data = bool(prices_repo.get_top("usd", 1))
            if not has_data:
                try:
                    run_etl(budget=budget)
                    path_taken = "ETL"
                except DataUnavailable:
                    if settings.use_seed_on_failure:
                        load_seed()
                        path_taken = "seed"
                except OperationalError as exc:
                    logger.warning("startup ETL failed: %s", exc)
                    if settings.use_seed_on_failure:
                        load_seed()
                        path_taken = "seed"
        session.commit()
    finally:
        session.close()

    try:
        sync_fear_greed_index()
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("startup fear & greed sync skipped: %s", exc)

    if logger.isEnabledFor(logging.INFO):
        logger.info("startup path: %s", path_taken)
    else:
        logger.warning("startup path: %s", path_taken)
    logging.getLogger().warning("startup path: %s", path_taken)
    asyncio.create_task(etl_loop())


app.mount("/", StaticFiles(directory="frontend", html=True), name="static")


__all__ = ["app", "etl_loop", "refresh_interval_seconds"]
