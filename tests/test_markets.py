from types import SimpleNamespace

import backend.app.main as main_module


def test_markets_endpoint():
    class DummyClient:
        def get_markets(self, vs="usd", per_page=20, page=1, order="market_cap_desc"):
            return [{"name": "Bitcoin", "symbol": "btc", "current_price": 123}]

    req = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(cg_client=DummyClient())))
    resp = main_module.markets(request=req, limit=1)
    assert len(resp) == 1
    item = resp[0]
    assert item["name"] == "Bitcoin"
    assert item["symbol"] == "BTC"
    assert item["price"] == 123
    assert item["score"] == 0.0
