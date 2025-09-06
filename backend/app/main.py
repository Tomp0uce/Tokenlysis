from functools import lru_cache
import asyncio
import os
from pathlib import Path
from typing import Dict, List

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .etl.run import run_etl
from .schemas.crypto import (
    CryptoDetail,
    CryptoSummary,
    HistoryPoint,
    HistoryResponse,
    Latest,
    RankingResponse,
    Scores,
)

app = FastAPI(title="Tokenlysis")
origins = os.getenv("CORS_ORIGINS", "http://localhost").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)

static_dir = Path(__file__).resolve().parents[2] / "frontend"
app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")


@lru_cache
def get_data() -> Dict[int, dict]:
    return run_etl()


def _latest_record(history: List[dict]) -> dict:
    return history[-1]


api = APIRouter(prefix="/api")


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
    get_data()

    async def _refresh_loop() -> None:
        while True:
            await asyncio.sleep(24 * 60 * 60)
            get_data.cache_clear()
            get_data()

    asyncio.create_task(_refresh_loop())


__all__ = ["app"]
