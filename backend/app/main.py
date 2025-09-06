from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .etl.run import run_etl

app = FastAPI(title="Tokenlysis")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA = run_etl()


def _latest_record(history):
    return history[-1]


@app.get("/api/cryptos")
def list_cryptos(limit: int = 20, sort: str = "score_global", order: str = "desc", page: int = 1, search: str | None = None):
    items = []
    for cid, cdata in DATA.items():
        latest = _latest_record(cdata['history'])
        item = {
            'id': cid,
            'symbol': cdata['symbol'],
            'name': cdata['name'],
            'sectors': cdata['sectors'],
            'latest': {
                'date': latest['date'],
                'price_usd': latest['metrics']['price_usd'],
                'scores': {
                    'global': latest['scores']['score_global'],
                    'liquidite': latest['scores']['score_liquidite'],
                    'opportunite': latest['scores']['score_opportunite'],
                }
            }
        }
        if search and search.lower() not in (item['symbol'].lower() + item['name'].lower()):
            continue
        items.append(item)
    key_funcs = {
        'score_global': lambda x: x['latest']['scores']['global'],
        'score_liquidite': lambda x: x['latest']['scores']['liquidite'],
        'score_opportunite': lambda x: x['latest']['scores']['opportunite'],
        'market_cap_usd': lambda x: next(h for h in DATA[x['id']]['history'] if h['date']==x['latest']['date'])['metrics']['market_cap_usd'],
        'symbol': lambda x: x['symbol'],
    }
    reverse = order == 'desc'
    items.sort(key=key_funcs.get(sort, key_funcs['score_global']), reverse=reverse)
    total = len(items)
    start = (page - 1) * limit
    paginated = items[start:start + limit]
    return {
        'total': total,
        'page': page,
        'page_size': limit,
        'items': paginated
    }


@app.get("/api/cryptos/{crypto_id}")
def get_crypto(crypto_id: int):
    cdata = DATA.get(crypto_id)
    if not cdata:
        raise HTTPException(status_code=404)
    latest = _latest_record(cdata['history'])
    return {
        'id': crypto_id,
        'symbol': cdata['symbol'],
        'name': cdata['name'],
        'sectors': cdata['sectors'],
        'latest': {
            'date': latest['date'],
            'metrics': latest['metrics'],
            'scores': {
                'global': latest['scores']['score_global'],
                'liquidite': latest['scores']['score_liquidite'],
                'opportunite': latest['scores']['score_opportunite'],
            }
        }
    }


@app.get("/api/cryptos/{crypto_id}/history")
def crypto_history(crypto_id: int, fields: str = "score_global,price_usd"):
    cdata = DATA.get(crypto_id)
    if not cdata:
        raise HTTPException(status_code=404)
    fields_list = [f.strip() for f in fields.split(',') if f.strip()]
    series = []
    for h in cdata['history']:
        item = {'date': h['date']}
        for f in fields_list:
            if f in h['scores']:
                item[f] = h['scores'][f]
            elif f in h['metrics']:
                item[f] = h['metrics'][f]
        series.append(item)
    return {'series': series}


__all__ = ["app"]
