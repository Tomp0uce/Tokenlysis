import json
import logging
import time
from importlib import reload

import pytest
from fastapi.testclient import TestClient


def test_log_level_respects_env(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    import backend.app.core.settings as settings_module

    reload(settings_module)
    import backend.app.main as main_module

    reload(main_module)
    monkeypatch.setattr(main_module, "run_etl", lambda *_, **__: None)
    monkeypatch.setattr(main_module, "load_seed", lambda *_, **__: None)
    with TestClient(main_module.app):
        pass
    assert logging.getLogger().getEffectiveLevel() == logging.DEBUG
    logging.getLogger().setLevel(logging.WARNING)


def test_coingecko_client_logs_json(monkeypatch, caplog):
    from backend.app.services.coingecko import CoinGeckoClient

    class DummyResp:
        status_code = 200
        headers = {"X-Request-Id": "rid"}
        request = type("Req", (), {"headers": {}})()
        url = "https://api.coingecko.com/api/v3/coins/markets"

        def json(self):
            return []

        def raise_for_status(self):
            pass

    class DummySession:
        def __init__(self) -> None:
            self.headers = {}

        def mount(self, prefix, adapter):
            pass

        def get(self, url, params=None, timeout=None):
            return DummyResp()

    counter = {"v": 0.0}

    def fake_perf_counter() -> float:
        counter["v"] += 0.001
        return counter["v"]

    monkeypatch.setattr(time, "perf_counter", fake_perf_counter)
    monkeypatch.setattr(time, "sleep", lambda s: None)

    client = CoinGeckoClient(api_key=None, session=DummySession())
    with caplog.at_level("INFO"):
        client.get_markets()
    record = next(r for r in caplog.records if r.message.startswith("{"))
    payload = json.loads(record.message)
    assert payload["endpoint"] == "/coins/markets"
    assert "latency_ms" in payload
