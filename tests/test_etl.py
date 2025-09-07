import importlib
from types import SimpleNamespace

import pytest

import backend.app.core.settings as settings_module
import backend.app.etl.run as run_module
from backend.app.etl.run import _coin_history


class DummyClient:
    def __init__(self) -> None:
        self.called_with = None

    def get_market_chart(self, coin_id: str, days: int, vs: str = "usd"):
        self.called_with = (coin_id, days, vs)
        return {"prices": []}


def test_coin_history_uses_coingecko_id():
    coin = {"coingecko_id": "bitcoin", "symbol": "btc", "id": "btc"}
    client = DummyClient()
    _coin_history(coin, 14, client)
    assert client.called_with == ("bitcoin", 14, "usd")


def test_coin_history_maps_seed_symbol():
    coin = {"symbol": "C1", "id": "1"}
    client = DummyClient()
    _coin_history(coin, 14, client)
    assert client.called_with == ("bitcoin", 14, "usd")


def _boom(*args, **kwargs):  # helper for failing ETL
    raise RuntimeError("boom")


def test_run_etl_seed_fallback(monkeypatch):
    monkeypatch.setenv("USE_SEED_ON_FAILURE", "true")
    importlib.reload(settings_module)
    importlib.reload(run_module)
    monkeypatch.setattr(run_module, "_coingecko_etl", _boom)
    dummy = SimpleNamespace(api_key=None)
    data = run_module.run_etl(dummy)
    assert data


def test_run_etl_raises_when_disabled(monkeypatch):
    monkeypatch.setenv("USE_SEED_ON_FAILURE", "false")
    importlib.reload(settings_module)
    importlib.reload(run_module)
    monkeypatch.setattr(run_module, "_coingecko_etl", _boom)
    dummy = SimpleNamespace(api_key=None)
    with pytest.raises(run_module.DataUnavailable):
        run_module.run_etl(dummy)


def test_to_daily_close():
    pairs = [[0, 1.0], [1000 * 60 * 60 * 23, 2.0], [1000 * 60 * 60 * 25, 3.0]]
    result = run_module.to_daily_close(pairs)
    assert len(result) == 2
    assert result[0][1] == 2.0
    assert result[1][1] == 3.0
