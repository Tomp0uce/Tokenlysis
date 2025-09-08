from __future__ import annotations

import asyncio
import datetime as dt
import logging
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError

from .core.settings import effective_coingecko_base_url, settings
from .core.version import get_version
from .db import Base, engine, get_session
from .db.migrations import run_migrations
from .etl.run import DataUnavailable, load_seed, run_etl
from .schemas.version import VersionResponse
from .services.budget import CallBudget
from .services.dao import PricesRepo, MetaRepo, CoinsRepo

logger = logging.getLogger(__name__)

app = FastAPI(title="Tokenlysis", version=os.getenv("APP_VERSION", "dev"))
@app.get("/info")
def info():
    return {
        "version": os.getenv("APP_VERSION", "dev"),
        "commit": os.getenv("GIT_COMMIT", "unknown"),
        "build_time": os.getenv("BUILD_TIME", "")
    }
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)


def _serialize_price(p, categories: tuple[list[str], list[str]]) -> dict:
    names, ids = categories
    return {
        "coin_id": p.coin_id,
        "vs_currency": p.vs_currency,
        "price": p.price,
        "market_cap": p.market_cap,
        "volume_24h": p.volume_24h,
        "rank": p.rank,
        "pct_change_24h": p.pct_change_24h,
        "snapshot_at": p.snapshot_at,
        "category_names": names,
        "category_ids": ids,
    }


@app.get("/api/markets/top")
def markets_top(
    limit: int = 20,
    vs: str = "usd",
    session: Session = Depends(get_session),
):
    vs = vs.lower()
    if vs != "usd":
        raise HTTPException(status_code=400, detail="unsupported vs")
    limit_effective = min(max(limit, 1), settings.CG_TOP_N)
    logger.info("markets_top", extra={"limit_effective": limit_effective, "vs": vs})
    prices_repo = PricesRepo(session)
    meta_repo = MetaRepo(session)
    coins_repo = CoinsRepo(session)
    rows = prices_repo.get_top(vs, limit_effective)
    categories_map = coins_repo.get_categories_bulk([r.coin_id for r in rows])
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
            _serialize_price(r, categories_map.get(r.coin_id, ([], []))) for r in rows
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
    prices_repo = PricesRepo(session)
    coins_repo = CoinsRepo(session)
    row = prices_repo.get_price(coin_id, vs)
    if row is None:
        raise HTTPException(status_code=404)
    cats = coins_repo.get_categories(coin_id)
    return _serialize_price(row, cats)


@app.get("/api/coins/{coin_id}/categories")
def coin_categories(coin_id: str, session: Session = Depends(get_session)) -> dict:
    coins_repo = CoinsRepo(session)
    names, ids = coins_repo.get_categories(coin_id)
    return {"category_names": names, "category_ids": ids}


@app.get("/api/diag")
def diag(session: Session = Depends(get_session)) -> dict:
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
    meta_repo = MetaRepo(session)
    last_refresh_at = meta_repo.get("last_refresh_at")
    return {"last_refresh_at": last_refresh_at}


def refresh_interval_seconds(value: str | None = None) -> int:
    granularity = value or settings.REFRESH_GRANULARITY
    try:
        if granularity.endswith("h"):
            return int(float(granularity[:-1]) * 60 * 60)
    except Exception:  # pragma: no cover - defensive
        pass
    return 12 * 60 * 60


async def etl_loop() -> None:
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
    try:
        session.execute(text("SELECT 1"))
    except Exception:  # pragma: no cover - defensive
        raise HTTPException(status_code=503)
    return {"ready": True}


@app.get("/version", response_model=VersionResponse)
@app.get("/api/version", response_model=VersionResponse, include_in_schema=False)
def version() -> VersionResponse:
    return VersionResponse(version=get_version())


@app.on_event("startup")
async def startup() -> None:
    logging.basicConfig(
        level=settings.log_level or "INFO",
        format="%(message)s",
        force=True,
    )
    logger.info("startup", extra={"version": get_version()})
    run_migrations()
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

    logger.info("startup path: %s", path_taken)
    asyncio.create_task(etl_loop())


app.mount("/", StaticFiles(directory="frontend", html=True), name="static")


__all__ = ["app", "etl_loop", "refresh_interval_seconds"]
