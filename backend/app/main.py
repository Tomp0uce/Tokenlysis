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

from .core.settings import settings
from .core.version import get_version
from .db import Base, engine, get_session
from .etl.run import DataUnavailable, load_seed, run_etl
from .schemas.version import VersionResponse
from .services.budget import CallBudget
from .services.dao import PricesRepo, MetaRepo

logger = logging.getLogger(__name__)

app = FastAPI(title="Tokenlysis")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)


def _serialize_price(p) -> dict:
    return {
        "coin_id": p.coin_id,
        "vs_currency": p.vs_currency,
        "price": p.price,
        "market_cap": p.market_cap,
        "volume_24h": p.volume_24h,
        "rank": p.rank,
        "pct_change_24h": p.pct_change_24h,
        "snapshot_at": p.snapshot_at,
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
    rows = prices_repo.get_top(vs, limit_effective)
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
        "items": [_serialize_price(r) for r in rows],
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
    row = prices_repo.get_price(coin_id, vs)
    if row is None:
        raise HTTPException(status_code=404)
    return _serialize_price(row)


@app.get("/healthz")
def healthz(session: Session = Depends(get_session)) -> dict:
    db_connected = True
    try:
        session.execute(text("SELECT 1"))
    except Exception:  # pragma: no cover - defensive
        db_connected = False

    bootstrap_done = False
    last_refresh_at = None
    monthly_call_count = 0
    if db_connected:
        meta_repo = MetaRepo(session)
        last_refresh_at = meta_repo.get("last_refresh_at")
        bootstrap_done = meta_repo.get("bootstrap_done") == "true"
        monthly_call_count = int(meta_repo.get("monthly_call_count") or 0)
    quota = settings.CG_MONTHLY_QUOTA
    return {
        "db_connected": db_connected,
        "bootstrap_done": bootstrap_done,
        "last_refresh_at": last_refresh_at,
        "monthly_call_count": monthly_call_count,
        "quota": quota,
        "ready": db_connected and bootstrap_done,
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
    Base.metadata.create_all(bind=engine)
    budget = None
    if settings.BUDGET_FILE:
        path = Path(settings.BUDGET_FILE)
        path.parent.mkdir(parents=True, exist_ok=True)
        budget = CallBudget(path, settings.CG_MONTHLY_QUOTA)
    app.state.budget = budget

    session = next(get_session())
    meta_repo = MetaRepo(session)
    try:
        if meta_repo.get("bootstrap_done") != "true":
            try:
                run_etl(budget=budget)
            except DataUnavailable:
                load_seed()
            meta_repo.set("bootstrap_done", "true")
        else:
            load_seed()
        session.commit()
    finally:
        session.close()

    async def _job() -> None:
        while True:
            try:
                run_etl(budget=app.state.budget)
            except DataUnavailable as exc:  # pragma: no cover - network failures
                logger.warning("ETL skipped: %s", exc)
            await asyncio.sleep(12 * 60 * 60)

    asyncio.create_task(_job())


app.mount("/", StaticFiles(directory="frontend", html=True), name="static")


__all__ = ["app"]
