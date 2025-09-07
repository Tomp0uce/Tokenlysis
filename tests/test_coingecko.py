from unittest.mock import Mock
import importlib

import backend.app.core.settings as settings_module
import backend.app.services.coingecko as coingecko
from backend.app.main import get_price


def _mock_session(json_data):
    session = Mock()
    response = Mock()
    response.json.return_value = json_data
    response.raise_for_status.return_value = None
    session.get.return_value = response
    session.headers = {}
    return session


def test_coingecko_client_price():
    session = _mock_session({"bitcoin": {"usd": 123.0}})
    client = coingecko.CoinGeckoClient(session=session)
    data = client.get_simple_price(["bitcoin"], ["usd"])
    assert data["bitcoin"]["usd"] == 123.0
    session.get.assert_called_once()


def test_get_price_endpoint():
    class DummyClient:
        def get_simple_price(self, coin_ids, vs_currencies):
            return {"bitcoin": {"usd": 456.0}}

    resp = get_price("bitcoin", client=DummyClient())
    assert resp.coin_id == "bitcoin"
    assert resp.usd == 456.0


def test_coingecko_client_adds_api_key(monkeypatch):
    monkeypatch.setenv("COINGECKO_API_KEY", "secret")
    importlib.reload(settings_module)
    importlib.reload(coingecko)
    session = _mock_session({})
    client = coingecko.CoinGeckoClient(session=session)
    assert client.session.headers["x-cg-pro-api-key"] == "secret"


def test_get_market_chart_uses_params():
    session = _mock_session({"prices": []})
    client = coingecko.CoinGeckoClient(session=session)
    client.get_market_chart("bitcoin", 14)
    session.get.assert_called_once()
    url, kwargs = session.get.call_args
    assert "coins/bitcoin/market_chart" in url[0]
    assert kwargs["params"] == {
        "vs_currency": "usd",
        "days": 14,
        "interval": "daily",
    }
