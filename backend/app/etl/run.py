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
from ..core.settings import settings
from ..services.indicators import rsi
from ..services.scoring import score_global, score_liquidite, score_opportunite
from ..config.seed_mapping import SEED_TO_COINGECKO

SEED_DIR = Path(__file__).resolve().parents[2] / "seed"


def _top_coins(limit: int, client: CoinGeckoClient) -> List[dict]:
    return client.get_markets(per_page=limit)


def _coin_history(coin: dict, days: int, client: CoinGeckoClient) -> dict:
    coin_id = (
        coin.get("coingecko_id")
        or SEED_TO_COINGECKO.get(coin.get("symbol", ""))
        or coin.get("id")
    )
    return client.get_market_chart(coin_id, days)


def _coingecko_etl(limit: int, days: int, client: CoinGeckoClient) -> Dict[int, Dict]:
    coins = _top_coins(limit, client)

    prices: Dict[int, List[float]] = {}
    volumes: Dict[int, List[float]] = {}
    mcaps: Dict[int, List[float]] = {}
    cryptos: Dict[int, dict] = {}

    for idx, coin in enumerate(coins, start=1):
        hist = _coin_history(coin, days, client)
        prices[idx] = [p[1] for p in hist.get("prices", [])][:days]
        volumes[idx] = [v[1] for v in hist.get("total_volumes", [])][:days]
        mcaps[idx] = [m[1] for m in hist.get("market_caps", [])][:days]
        cryptos[idx] = {
            "id": idx,
            "symbol": coin["symbol"],
            "name": coin["name"],
            "sectors": [],
        }

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


def run_etl() -> Dict[int, Dict]:
    """Return structured market data for a list of assets."""

    limit = settings.cg_top_n
    days = settings.cg_days
    client = CoinGeckoClient()
    try:
        return _coingecko_etl(limit, days, client)
    except Exception:
        logging.exception("Falling back to seed data")
        return _seed_etl()


if __name__ == "__main__":
    run_etl()
