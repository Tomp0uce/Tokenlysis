import importlib
import pytest

import backend.app.core.settings as settings_module
from backend.app.etl.run import _coin_history


class DummyClient:
    def __init__(self) -> None:
        self.called_with = None

    def get_market_chart(self, coin_id: str, days: int, interval: str | None = None):
        self.called_with = (coin_id, days, interval)
        return {"prices": []}


def test_coin_history_uses_coingecko_id():
    coin = {"coingecko_id": "bitcoin", "symbol": "btc", "id": "btc"}
    client = DummyClient()
    _coin_history(coin, 14, client)
    assert client.called_with == ("bitcoin", 14, None)


def test_coin_history_maps_seed_symbol():
    coin = {"symbol": "C1", "id": "1"}
    client = DummyClient()
    _coin_history(coin, 14, client)
    assert client.called_with == ("bitcoin", 14, None)


def _boom(*args, **kwargs):  # helper for failing ETL
    raise RuntimeError("boom")


def test_run_etl_seed_fallback(monkeypatch):
    monkeypatch.setenv("USE_SEED_ON_FAILURE", "true")
    importlib.reload(settings_module)
    import backend.app.etl.run as run_module

    importlib.reload(run_module)
    monkeypatch.setattr(run_module, "_coingecko_etl", _boom)
    data = run_module.run_etl()
    assert data


def test_run_etl_raises_when_disabled(monkeypatch):
    monkeypatch.setenv("USE_SEED_ON_FAILURE", "false")
    importlib.reload(settings_module)
    import backend.app.etl.run as run_module

    importlib.reload(run_module)
    monkeypatch.setattr(run_module, "_coingecko_etl", _boom)
    with pytest.raises(run_module.DataUnavailable):
        run_module.run_etl()
