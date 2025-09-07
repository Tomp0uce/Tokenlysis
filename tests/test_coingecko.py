from unittest.mock import Mock
import importlib
import requests

import backend.app.core.settings as settings_module
import backend.app.services.coingecko as coingecko
from backend.app.main import get_price


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


def test_simple_price_cache(monkeypatch):
    session = _mock_session({"bitcoin": {"usd": 1}})
    client = coingecko.CoinGeckoClient(session=session, price_ttl=60)
    client.get_simple_price(["bitcoin"], ["usd"])
    client.get_simple_price(["bitcoin"], ["usd"])
    assert session.get.call_count == 1


def test_retry_on_429(monkeypatch):
    resp1 = Mock(
        status_code=429,
        headers={},
        json=lambda: {},
        raise_for_status=Mock(side_effect=requests.HTTPError()),
    )
    resp2 = Mock(
        status_code=200,
        headers={},
        json=lambda: {"ok": True},
        raise_for_status=Mock(),
    )
    session = Mock()
    session.get.side_effect = [resp1, resp2]
    session.headers = {}
    client = coingecko.CoinGeckoClient(session=session, max_retries=2)
    data = client.get_simple_price(["btc"], ["usd"])
    assert data == {"ok": True}
    assert session.get.call_count == 2
