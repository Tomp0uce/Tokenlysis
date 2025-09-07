from types import SimpleNamespace
from unittest.mock import Mock
import importlib
import requests
from fastapi.testclient import TestClient

import backend.app.core.settings as settings_module
import backend.app.services.coingecko as coingecko
from backend.app.main import app, get_price

coingecko.settings.CG_THROTTLE_MS = 0


def _mock_session(json_data):
    session = Mock()
    response = Mock()
    response.json.return_value = json_data
    response.raise_for_status.return_value = None
    response.status_code = 200
    response.headers = {}
    response.request = SimpleNamespace(headers={})
    response.url = "http://test"
    session.get.return_value = response
    session.headers = {}
    session.mount = Mock()
    return session


def test_coingecko_client_price():
    session = _mock_session({"bitcoin": {"usd": 123.0}})
    client = coingecko.CoinGeckoClient(api_key=None, session=session)
    data = client.get_simple_price(["bitcoin"], ["usd"])
    assert data["bitcoin"]["usd"] == 123.0
    session.get.assert_called_once()


def test_get_price_endpoint():
    class DummyClient:
        def get_simple_price(self, coin_ids, vs_currencies):
            return {"bitcoin": {"usd": 456.0}}

    req = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(cg_client=DummyClient()))
    )
    resp = get_price("bitcoin", req)
    assert resp.coin_id == "bitcoin"
    assert resp.usd == 456.0


def test_coingecko_client_adds_api_key():
    session = _mock_session({})
    client = coingecko.CoinGeckoClient(api_key="secret", plan="pro", session=session)
    assert client.session.headers["x-cg-api-key"] == "secret"
    assert client.base_url == coingecko.BASE_URL
    client_demo = coingecko.CoinGeckoClient(api_key="demo", plan="demo", session=_mock_session({}))
    assert client_demo.session.headers["x-cg-demo-api-key"] == "demo"


def test_get_market_chart_uses_params(monkeypatch):
    session = _mock_session({"prices": []})
    monkeypatch.setattr(coingecko.time, "sleep", lambda x: None)
    client = coingecko.CoinGeckoClient(api_key=None, session=session)
    client.get_market_chart("bitcoin", 14)
    session.get.assert_called()
    url, kwargs = session.get.call_args
    assert "coins/bitcoin/market_chart" in url[0]
    params = kwargs["params"]
    assert params["vs_currency"] == "usd"
    assert params["days"] == 14
    assert "interval" not in params


def test_diag_cg(monkeypatch):
    class DummyResp:
        def json(self):
            return {"gecko_says": "(pong)"}

    class DummyClient:
        api_key = "k"
        base_url = coingecko.BASE_URL

        def _request(self, path, params=None):
            return DummyResp()

        def get_markets(self, per_page=1, page=1, vs_currency="usd"):
            return [{"id": "btc"}]

        def get_market_chart(self, coin_id, days, vs="usd"):
            return {"prices": [[0, 0], [1, 1]]}

    monkeypatch.setenv("COINGECKO_API_KEY", "k")
    monkeypatch.setenv("COINGECKO_PLAN", "pro")
    importlib.reload(settings_module)
    importlib.reload(coingecko)
    import backend.app.main as main_module
    importlib.reload(main_module)
    main_module.app.state.cg_client = DummyClient()
    client = TestClient(main_module.app)
    resp = client.get("/api/diag/cg")
    assert resp.status_code == 200
    data = resp.json()
    assert data["plan"] == "pro"
    assert data["base_url"] == coingecko.BASE_URL
    assert data["has_api_key"] is True
    assert data["granularity"] == "daily"
    assert data["diag"]["chart_points"] == 2
