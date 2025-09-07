import asyncio
import datetime as dt
from functools import lru_cache
from pathlib import Path
from typing import Dict, List
from uuid import uuid4

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .core.log import request_id_ctx
from .core.scheduling import seconds_until_next_midnight_utc
from .core.settings import settings, mask_secret
from .core.version import get_version
from .etl.run import DataUnavailable, run_etl
from .schemas.crypto import (
    CryptoDetail,
    CryptoSummary,
    HistoryPoint,
    HistoryResponse,
    Latest,
    RankingResponse,
    Scores,
)
from .schemas.price import PriceResponse
from .schemas.version import VersionResponse
from .services.coingecko import CoinGeckoClient

import logging


_NAME_MAP = {
    **logging._nameToLevel,
    "WARN": logging.WARNING,
    "FATAL": logging.CRITICAL,
}


def parse_log_level(raw: str | int | None, default: int = logging.INFO) -> int:
    """Parse log level names or integers, defaulting when unknown."""

    if raw is None:
        return default
    if isinstance(raw, int):
        return raw
    s = str(raw).strip().upper()
    if s == "":
        return default
    if s.isdigit():
        return int(s)
    return _NAME_MAP.get(s, default)


logger = logging.getLogger(__name__)

lvl = parse_log_level(settings.log_level)
if isinstance(settings.log_level, str):
    s = settings.log_level.strip().upper()
    if s and not s.isdigit() and s not in _NAME_MAP:
        logger.warning(
            "LOG_LEVEL=%r non reconnu, fallback sur %s",
            settings.log_level,
            logging.getLevelName(lvl),
        )

logging.basicConfig(level=lvl, format="%(message)s")
for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
    logging.getLogger(name).setLevel(lvl)

logger.info(
    (
        "Startup config: LOG_LEVEL=%s USE_SEED_ON_FAILURE=%s CG_TOP_N=%s "
        "CG_DAYS=%s COINGECKO_API_KEY=%s"
    ),
    logging.getLevelName(lvl),
    settings.use_seed_on_failure,
    settings.CG_TOP_N,
    settings.CG_DAYS,
    mask_secret(settings.COINGECKO_API_KEY),
)

app = FastAPI(title="Tokenlysis")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    rid = request.headers.get("X-Request-ID") or str(uuid4())
    if request_id_ctx is not None:
        request_id_ctx.set(rid)
    response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    return response


@lru_cache
def get_data() -> Dict[int, dict]:
    try:
        return run_etl()
    except DataUnavailable as exc:  # pragma: no cover - handled by API
        raise HTTPException(status_code=503, detail="data unavailable") from exc


def _latest_record(history: List[dict]) -> dict:
    return history[-1]


def get_coingecko_client() -> CoinGeckoClient:
    """Dependency that returns a CoinGeckoClient instance."""
    return CoinGeckoClient()


api = APIRouter(prefix="/api")


@api.get("/version", response_model=VersionResponse)
def read_version() -> VersionResponse:
    """Return application version."""
    return VersionResponse(version=get_version())


@api.get("/diag")
def diag(client: CoinGeckoClient = Depends(get_coingecko_client)) -> dict:
    """Return diagnostic information."""
    api_key_masked = mask_secret(settings.COINGECKO_API_KEY)
    try:
        ping = client.ping()
        outbound_ok = True
    except Exception:
        ping = ""
        outbound_ok = False
    return {
        "app_version": get_version(),
        "outbound_ok": outbound_ok,
        "coingecko_ping": ping,
        "api_key_masked": api_key_masked,
    }


@api.get("/price/{coin_id}", response_model=PriceResponse)
def get_price(
    coin_id: str, client: CoinGeckoClient = Depends(get_coingecko_client)
) -> PriceResponse:
    data = client.get_simple_price([coin_id], ["usd"])
    price = data.get(coin_id, {}).get("usd")
    if price is None:
        raise HTTPException(status_code=404, detail="Price not found")
    return PriceResponse(coin_id=coin_id, usd=price)


@api.get("/ranking", response_model=RankingResponse)
def list_cryptos(
    limit: int = 20,
    sort: str = "score_global",
    order: str = "desc",
    page: int = 1,
    search: str | None = None,
    data: Dict[int, dict] = Depends(get_data),
) -> RankingResponse:
    items: List[CryptoSummary] = []
    for cid, cdata in data.items():
        latest = _latest_record(cdata["history"])
        latest_model = Latest(
            date=latest["date"],
            price_usd=latest["metrics"]["price_usd"],
            scores=Scores(
                global_=latest["scores"]["score_global"],
                liquidite=latest["scores"]["score_liquidite"],
                opportunite=latest["scores"]["score_opportunite"],
            ),
        )
        crypto = CryptoSummary(
            id=cid,
            symbol=cdata["symbol"],
            name=cdata["name"],
            sectors=cdata["sectors"],
            latest=latest_model,
        )
        if search and search.lower() not in (
            crypto.symbol.lower() + crypto.name.lower()
        ):
            continue
        items.append(crypto)
    key_funcs = {
        "score_global": lambda x: x.latest.scores.global_,
        "score_liquidite": lambda x: x.latest.scores.liquidite,
        "score_opportunite": lambda x: x.latest.scores.opportunite,
        "market_cap_usd": lambda x: next(
            h for h in data[x.id]["history"] if h["date"] == x.latest.date
        )["metrics"]["market_cap_usd"],
        "symbol": lambda x: x.symbol,
    }
    reverse = order == "desc"
    items.sort(key=key_funcs.get(sort, key_funcs["score_global"]), reverse=reverse)
    total = len(items)
    start = (page - 1) * limit
    paginated = items[start : start + limit]
    return RankingResponse(total=total, page=page, page_size=limit, items=paginated)


@api.get("/asset/{crypto_id}", response_model=CryptoDetail)
def get_crypto(
    crypto_id: int, data: Dict[int, dict] = Depends(get_data)
) -> CryptoDetail:
    cdata = data.get(crypto_id)
    if not cdata:
        raise HTTPException(status_code=404)
    latest = _latest_record(cdata["history"])
    latest_model = Latest(
        date=latest["date"],
        metrics=latest["metrics"],
        scores=Scores(
            global_=latest["scores"]["score_global"],
            liquidite=latest["scores"]["score_liquidite"],
            opportunite=latest["scores"]["score_opportunite"],
        ),
    )
    return CryptoDetail(
        id=crypto_id,
        symbol=cdata["symbol"],
        name=cdata["name"],
        sectors=cdata["sectors"],
        latest=latest_model,
    )


@api.get("/history/{crypto_id}", response_model=HistoryResponse)
def crypto_history(
    crypto_id: int,
    fields: str = "score_global,price_usd",
    data: Dict[int, dict] = Depends(get_data),
) -> HistoryResponse:
    cdata = data.get(crypto_id)
    if not cdata:
        raise HTTPException(status_code=404)
    fields_list = [f.strip() for f in fields.split(",") if f.strip()]
    series = []
    for h in cdata["history"]:
        item = {"date": h["date"]}
        for f in fields_list:
            if f in h["scores"]:
                item[f] = h["scores"][f]
            elif f in h["metrics"]:
                item[f] = h["metrics"][f]
        series.append(item)
    return HistoryResponse(series=[HistoryPoint(**s) for s in series])


app.include_router(api)


@app.on_event("startup")
async def refresh_cache() -> None:
    try:
        get_data()
    except HTTPException:
        pass

    async def _refresh_loop() -> None:
        await asyncio.sleep(
            seconds_until_next_midnight_utc(dt.datetime.now(dt.timezone.utc))
        )
        while True:
            get_data.cache_clear()
            try:
                get_data()
            except HTTPException:
                pass
            await asyncio.sleep(24 * 60 * 60)

    asyncio.create_task(_refresh_loop())


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> dict:
    return {"ready": True}


static_dir = Path(__file__).resolve().parents[2] / "frontend"
app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")


__all__ = ["app"]
