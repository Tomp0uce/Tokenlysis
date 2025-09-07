"""ETL pipeline fetching real market data from CoinGecko.

This module replaces the previous seed-based implementation with live calls to
the public CoinGecko API. The ETL downloads the top ``CG_TOP_N`` assets and
their last ``CG_DAYS`` days of market data to compute the liquidity and
opportunity scores as well as a global score.

The number of assets and days can be configured via environment variables:

``CG_TOP_N``
    Number of assets to retrieve (default: 20).
``CG_DAYS``
    How many days of history to pull (default: 14).
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Dict, List

import logging

from ..services.coingecko import CoinGeckoClient
from ..core.settings import settings, effective_coingecko_base_url
from ..services.indicators import rsi
from ..services.scoring import score_global, score_liquidite, score_opportunite
from ..config.seed_mapping import SEED_TO_COINGECKO

SEED_DIR = Path(__file__).resolve().parents[2] / "seed"


def _top_coins(limit: int, client: CoinGeckoClient) -> List[dict]:
    per_page = min(250, max(50, limit)) if limit >= 50 else limit
    coins: List[dict] = []
    page = 1
    while len(coins) < limit:
        remaining = limit - len(coins)
        take = min(per_page, remaining)
        data = client.get_markets(per_page=take, page=page)
        if not data:
            break
        coins.extend(data)
        if len(data) < take:
            break
        page += 1
    return coins[:limit]


def _coin_history(coin: dict, days: int, client: CoinGeckoClient) -> dict:
    coin_id = (
        coin.get("coingecko_id")
        or SEED_TO_COINGECKO.get(coin.get("symbol", ""))
        or coin.get("id")
    )
    return client.get_market_chart(coin_id, days, interval=settings.CG_INTERVAL)


def _coingecko_etl(limit: int, days: int, client: CoinGeckoClient) -> Dict[int, Dict]:
    coins = _top_coins(limit, client)

    prices: Dict[int, List[float]] = {}
    volumes: Dict[int, List[float]] = {}
    mcaps: Dict[int, List[float]] = {}
    cryptos: Dict[int, dict] = {}
    errors = 0

    for idx, coin in enumerate(coins, start=1):
        try:
            hist = _coin_history(coin, days, client)
        except Exception as exc:  # pragma: no cover - network failures
            errors += 1
            logging.warning(f"history failed for {coin.get('id')}: {exc}")
            continue
        prices[idx] = [p[1] for p in hist.get("prices", [])][:days]
        volumes[idx] = [v[1] for v in hist.get("total_volumes", [])][:days]
        mcaps[idx] = [m[1] for m in hist.get("market_caps", [])][:days]
        cryptos[idx] = {
            "id": idx,
            "symbol": coin.get("symbol", ""),
            "name": coin.get("name", ""),
            "sectors": [],
        }

    if not cryptos:
        raise RuntimeError("Empty ETL result (all history calls failed)")

    rsi_map = {cid: rsi(arr) for cid, arr in prices.items()}
    volchg_map: Dict[int, List[float]] = {}
    for cid, vols in volumes.items():
        changes = [0.0]
        for i in range(1, len(vols)):
            prev = vols[i - 1]
            changes.append(((vols[i] - prev) / prev * 100) if prev else 0.0)
        volchg_map[cid] = changes

    start = dt.date.today() - dt.timedelta(days=days - 1)
    dates = [start + dt.timedelta(days=i) for i in range(days)]

    data: Dict[int, Dict] = {
        cid: {**info, "history": []} for cid, info in cryptos.items()
    }

    for day_idx, day in enumerate(dates):
        volume_arr = [volumes[cid][day_idx] for cid in cryptos]
        mcap_arr = [mcaps[cid][day_idx] for cid in cryptos]
        listings_arr = [0 for _ in cryptos]
        rsi_arr = [rsi_map[cid][day_idx] for cid in cryptos]
        volchg_arr = [volchg_map[cid][day_idx] for cid in cryptos]

        liq_scores = score_liquidite(volume_arr, mcap_arr, listings_arr)
        opp_scores = score_opportunite(rsi_arr, volchg_arr)
        glob_scores = score_global(liq_scores, opp_scores)

        for idx, cid in enumerate(cryptos):
            data[cid]["history"].append(
                {
                    "date": day.isoformat(),
                    "metrics": {
                        "price_usd": prices[cid][day_idx],
                        "market_cap_usd": mcap_arr[idx],
                        "volume_24h_usd": volume_arr[idx],
                        "listings_count": 0,
                        "rsi14": rsi_arr[idx],
                    },
                    "scores": {
                        "score_global": glob_scores[idx],
                        "score_liquidite": liq_scores[idx],
                        "score_opportunite": opp_scores[idx],
                    },
                }
            )

    logging.info(f"ETL done: coins={len(cryptos)} errors={errors}")
    return data


def _seed_etl() -> Dict[int, Dict]:
    with open(SEED_DIR / "cryptos.json") as f:
        cryptos = json.load(f)
    with open(SEED_DIR / "prices_last14d.json") as f:
        prices = json.load(f)
    cryptos_map = {int(c["id"]): c for c in cryptos}
    start = dt.date(2023, 1, 1)
    days = [start + dt.timedelta(days=i) for i in range(14)]

    data: Dict[int, Dict] = {}
    price_arrays: Dict[int, List[float]] = {}
    for cid, info in cryptos_map.items():
        series = prices[str(cid)]
        price_arrays[cid] = [p["price"] for p in series]

    rsi_map = {cid: rsi(arr) for cid, arr in price_arrays.items()}

    for day_idx, day in enumerate(days):
        volume_arr = []
        mcap_arr = []
        listings_arr = []
        rsi_arr = []
        volchg_arr = []
        for cid, info in cryptos_map.items():
            price = price_arrays[cid][day_idx]
            market_cap = price * 1_000_000
            volume = 100_000 + cid * 1_000 + day_idx * 100
            listings = 10 + cid
            if day_idx == 0:
                vol_change = 0.0
            else:
                prev = 100_000 + cid * 1_000 + (day_idx - 1) * 100
                vol_change = (volume - prev) / prev * 100
            volume_arr.append(volume)
            mcap_arr.append(market_cap)
            listings_arr.append(listings)
            rsi_arr.append(rsi_map[cid][day_idx])
            volchg_arr.append(vol_change)
        liq_scores = score_liquidite(volume_arr, mcap_arr, listings_arr)
        opp_scores = score_opportunite(rsi_arr, volchg_arr)
        glob_scores = score_global(liq_scores, opp_scores)

        for idx, cid in enumerate(cryptos_map):
            info = cryptos_map[cid]
            entry = data.setdefault(
                cid,
                {
                    "id": cid,
                    "symbol": info["symbol"],
                    "name": info["name"],
                    "sectors": info.get("sectors"),
                    "history": [],
                },
            )
            entry["history"].append(
                {
                    "date": day.isoformat(),
                    "metrics": {
                        "price_usd": price_arrays[cid][day_idx],
                        "market_cap_usd": mcap_arr[idx],
                        "volume_24h_usd": volume_arr[idx],
                        "listings_count": listings_arr[idx],
                        "rsi14": rsi_arr[idx],
                    },
                    "scores": {
                        "score_global": glob_scores[idx],
                        "score_liquidite": liq_scores[idx],
                        "score_opportunite": opp_scores[idx],
                    },
                }
            )
    return data


class DataUnavailable(Exception):
    """Raised when live data could not be fetched."""


def run_etl(client: CoinGeckoClient | None = None) -> Dict[int, Dict]:
    """Return structured market data for a list of assets."""

    if client is None:
        client = CoinGeckoClient(
            base_url=effective_coingecko_base_url(),
            api_key=settings.COINGECKO_API_KEY or settings.coingecko_api_key,
        )

    limit = max(
        10,
        min(settings.CG_TOP_N, 250 if client.api_key is None else settings.CG_TOP_N),
    )
    days = settings.CG_DAYS
    try:
        return _coingecko_etl(limit, days, client)
    except Exception as exc:  # pragma: no cover - network failures
        if settings.use_seed_on_failure:
            logging.exception("Falling back to seed data")
            return _seed_etl()
        logging.exception("ETL failure")
        raise DataUnavailable("data unavailable") from exc


if __name__ == "__main__":
    run_etl()
