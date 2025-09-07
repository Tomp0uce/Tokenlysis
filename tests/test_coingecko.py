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
    session.get.return_value = response
    session.headers = {}
    return session


def test_coingecko_client_price():
    session = _mock_session({"bitcoin": {"usd": 123.0}})
    client = coingecko.CoinGeckoClient(
        base_url=coingecko.PUB_BASE, api_key=None, session=session
    )
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
    client = coingecko.CoinGeckoClient(
        base_url=coingecko.PRO_BASE, api_key="secret", session=session
    )
    assert client.session.headers["x-cg-pro-api-key"] == "secret"
    assert client.base_url == coingecko.PRO_BASE


def test_get_market_chart_uses_params():
    session = _mock_session({"prices": []})
    client = coingecko.CoinGeckoClient(
        base_url=coingecko.PUB_BASE, api_key=None, session=session
    )
    client.get_market_chart("bitcoin", 14)
    session.get.assert_called()
    url, kwargs = session.get.call_args
    assert "coins/bitcoin/market_chart" in url[0]
    assert kwargs["params"] == {"vs_currency": "usd", "days": 14, "interval": "daily"}


def test_retry_on_429():
    resp1 = Mock(
        status_code=429,
        headers={},
        text="oops",
        json=lambda: {},
        raise_for_status=Mock(side_effect=requests.HTTPError("429")),
    )
    resp2 = Mock(
        status_code=200,
        headers={},
        json=lambda: {},
        raise_for_status=Mock(return_value=None),
    )
    session = Mock()
    session.get.side_effect = [resp1, resp2]
    session.headers = {}
    client = coingecko.CoinGeckoClient(
        base_url=coingecko.PUB_BASE, api_key=None, session=session
    )
    client.get_simple_price(["btc"], ["usd"])
    assert session.get.call_count == 2


def test_diag_cg(monkeypatch):
    class DummyResp:
        def json(self):
            return {"gecko_says": "(pong)"}

    class DummyClient:
        api_key = "k"
        base_url = coingecko.PRO_BASE

        def _request(self, path, params=None):
            return DummyResp()

        def get_markets(self, per_page=1, page=1, vs_currency="usd"):
            return [{"id": "btc"}]

        def get_market_chart(self, coin_id, days, vs="usd", interval=None):
            return {"prices": [[0, 0], [1, 1]]}

    monkeypatch.setenv("COINGECKO_API_KEY", "k")
    importlib.reload(settings_module)
    importlib.reload(coingecko)
    app.state.cg_client = DummyClient()
    client = TestClient(app)
    resp = client.get("/api/diag/cg")
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "pro"
    assert data["base_url_effective"] == coingecko.PRO_BASE
    assert data["has_api_key"] is True
    assert data["interval_effective"] == "daily"
    assert data["diag"]["chart_points"] == 2
