import json
import datetime
from pathlib import Path
from typing import Dict, List

from ..services.indicators import rsi
from ..services.scoring import score_liquidite, score_opportunite, score_global

BASE_DIR = Path(__file__).resolve().parent.parent
SEED_DIR = BASE_DIR.parent / 'seed'


def load_seed() -> Dict:
    with open(SEED_DIR / 'cryptos.json') as f:
        cryptos = json.load(f)
    with open(SEED_DIR / 'prices_last14d.json') as f:
        prices = json.load(f)
    return {int(c['id']): c for c in cryptos}, prices


def run_etl() -> Dict[int, Dict]:
    cryptos, prices = load_seed()
    start = datetime.date(2023, 1, 1)
    days = [start + datetime.timedelta(days=i) for i in range(14)]

    data: Dict[int, Dict] = {}
    # prepare price arrays per crypto
    price_arrays: Dict[int, List[float]] = {}
    for cid, info in cryptos.items():
        series = prices[str(cid)]
        price_arrays[cid] = [p['price'] for p in series]

    # compute RSI for each crypto
    rsi_map = {cid: rsi(arr) for cid, arr in price_arrays.items()}

    for day_idx, day in enumerate(days):
        volume_arr = []
        mcap_arr = []
        listings_arr = []
        rsi_arr = []
        volchg_arr = []
        for cid, info in cryptos.items():
            price = price_arrays[cid][day_idx]
            market_cap = price * 1_000_000
            volume = 100_000 + cid * 1_000 + day_idx * 100
            listings = 10 + cid
            # volume change pct
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

        for idx, cid in enumerate(cryptos):
            info = cryptos[cid]
            entry = data.setdefault(cid, {
                'id': cid,
                'symbol': info['symbol'],
                'name': info['name'],
                'sectors': info.get('sectors'),
                'history': []
            })
            entry['history'].append({
                'date': day.isoformat(),
                'metrics': {
                    'price_usd': price_arrays[cid][day_idx],
                    'market_cap_usd': mcap_arr[idx],
                    'volume_24h_usd': volume_arr[idx],
                    'listings_count': listings_arr[idx],
                    'rsi14': rsi_arr[idx],
                },
                'scores': {
                    'score_global': glob_scores[idx],
                    'score_liquidite': liq_scores[idx],
                    'score_opportunite': opp_scores[idx],
                }
            })
    return data

if __name__ == '__main__':
    run_etl()
