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
import logging
import math
from pathlib import Path
from typing import Dict, List

import requests

from ..services.coingecko import CoinGeckoClient
from ..services.budget import CallBudget
from ..core.settings import settings, effective_coingecko_base_url
from ..services.indicators import rsi
from ..services.scoring import score_global, score_liquidite, score_opportunite
from ..config.seed_mapping import SEED_TO_COINGECKO

SEED_DIR = Path(__file__).resolve().parents[2] / "seed"


def _top_coins(limit: int, client: CoinGeckoClient, per_page_max: int) -> List[dict]:
    per_page = per_page_max if limit > per_page_max else limit
    coins: List[dict] = []
    page = 1
    while len(coins) < limit:
        take = min(per_page, limit - len(coins))
        try:
            data = client.get_markets(vs="usd", per_page=take, page=page)
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response else 0
            if 400 <= status < 500 and per_page > 100:
                per_page = 100
                continue
            raise
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
    return client.get_market_chart(coin_id, days, vs="usd")


def to_daily_close(ms_price_pairs: List[List[float]]) -> List[tuple[dt.date, float]]:
    """Resample timestamped points to daily close values."""

    daily: Dict[dt.date, float] = {}
    for ms, price in ms_price_pairs:
        day = dt.datetime.fromtimestamp(ms / 1000, tz=dt.timezone.utc).date()
        daily[day] = price
    return sorted(daily.items())


def _coingecko_etl(
    limit: int, days: int, client: CoinGeckoClient, per_page_max: int
) -> Dict[int, Dict]:
    coins = _top_coins(limit, client, per_page_max)

    prices: Dict[int, List[float]] = {}
    volumes: Dict[int, List[float]] = {}
    mcaps: Dict[int, List[float]] = {}
    dates_map: Dict[int, List[dt.date]] = {}
    data: Dict[int, dict] = {}
    errors = 0

    for idx, coin in enumerate(coins, start=1):
        info = {
            "id": idx,
            "symbol": coin.get("symbol", ""),
            "name": coin.get("name", ""),
            "sectors": [],
        }
        try:
            hist = _coin_history(coin, days, client)
            price_pairs = to_daily_close(hist.get("prices", []))
            vol_pairs = to_daily_close(hist.get("total_volumes", []))
            mcap_pairs = to_daily_close(hist.get("market_caps", []))
            if len(price_pairs) < days:
                raise ValueError("history too short")
            price_pairs = price_pairs[-days:]
            vol_pairs = vol_pairs[-days:]
            mcap_pairs = mcap_pairs[-days:]
            prices[idx] = [p for _, p in price_pairs]
            volumes[idx] = [v for _, v in vol_pairs]
            mcaps[idx] = [m for _, m in mcap_pairs]
            dates_map[idx] = [d for d, _ in price_pairs]
            data[idx] = {**info, "history": []}
        except Exception as exc:  # pragma: no cover - network failures
            errors += 1
            logging.warning(f"history failed for {coin.get('id')}: {exc}")
            today = dt.date.today().isoformat()
            data[idx] = {
                **info,
                "history": [
                    {
                        "date": today,
                        "metrics": {
                            "price_usd": coin.get("current_price"),
                            "market_cap_usd": coin.get("market_cap"),
                            "volume_24h_usd": coin.get("total_volume"),
                            "listings_count": 0,
                            "rsi14": 0.0,
                        },
                        "scores": {
                            "score_global": 0.0,
                            "score_liquidite": 0.0,
                            "score_opportunite": 0.0,
                        },
                    }
                ],
            }

    success_ids = [cid for cid in data if cid in dates_map]
    if not success_ids:
        logging.error("Empty ETL result (all history calls failed)")
        return data

    rsi_map = {cid: rsi(prices[cid]) for cid in success_ids}
    volchg_map: Dict[int, List[float]] = {}
    for cid in success_ids:
        vols = volumes[cid]
        changes = [0.0]
        for i in range(1, len(vols)):
            prev = vols[i - 1]
            changes.append(((vols[i] - prev) / prev * 100) if prev else 0.0)
        volchg_map[cid] = changes

    dates = dates_map[success_ids[0]]

    for day_idx, day in enumerate(dates):
        volume_arr = [volumes[cid][day_idx] for cid in success_ids]
        mcap_arr = [mcaps[cid][day_idx] for cid in success_ids]
        listings_arr = [0 for _ in success_ids]
        rsi_arr = [rsi_map[cid][day_idx] for cid in success_ids]
        volchg_arr = [volchg_map[cid][day_idx] for cid in success_ids]

        liq_scores = score_liquidite(volume_arr, mcap_arr, listings_arr)
        opp_scores = score_opportunite(rsi_arr, volchg_arr)
        glob_scores = score_global(liq_scores, opp_scores)

        for idx, cid in enumerate(success_ids):
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

    logging.info(f"ETL done: coins={len(data)} errors={errors}")
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


def run_etl(
    client: CoinGeckoClient | None = None, budget: CallBudget | None = None
) -> Dict[int, Dict]:
    """Return structured market data for a list of assets."""

    if client is None:
        client = CoinGeckoClient(
            base_url=effective_coingecko_base_url(),
            api_key=settings.COINGECKO_API_KEY or settings.coingecko_api_key,
        )

    if budget is None and settings.BUDGET_FILE:
        budget = CallBudget(Path(settings.BUDGET_FILE), settings.CG_MONTHLY_QUOTA)

    limit = max(
        10,
        min(settings.CG_TOP_N, 250 if client.api_key is None else settings.CG_TOP_N),
    )
    days = settings.CG_DAYS
    per_page_max = settings.CG_PER_PAGE_MAX
    required_calls = math.ceil(limit / per_page_max)
    if budget and not budget.can_spend(required_calls):
        raise DataUnavailable("quota exceeded")
    try:
        data = _coingecko_etl(limit, days, client, per_page_max)
        if budget:
            budget.spend(required_calls)
        return data
    except Exception as exc:  # pragma: no cover - network failures
        if settings.use_seed_on_failure:
            logging.exception("Falling back to seed data")
            return _seed_etl()
        logging.exception("ETL failure")
        raise DataUnavailable("data unavailable") from exc


if __name__ == "__main__":
    run_etl()
