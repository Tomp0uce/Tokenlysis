import json
import logging
import time
from importlib import reload

import pytest
import requests
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

    client = CoinGeckoClient(api_key=None, plan="pro", session=DummySession())
    with caplog.at_level("INFO"):
        client.get_markets()
    record = next(r for r in caplog.records if r.message.startswith("{"))
    payload = json.loads(record.message)
    assert payload["endpoint"] == "/coins/markets"
    assert "latency_ms" in payload


def test_coingecko_client_throttles_and_logs_demo(monkeypatch, caplog):
    from backend.app.core import settings as settings_module
    from backend.app.services.coingecko import CoinGeckoClient

    monkeypatch.setattr(settings_module.settings, "CG_THROTTLE_MS", 100)

    from types import SimpleNamespace

    class DummySession:
        def __init__(self) -> None:
            self.headers: dict = {}

        def mount(self, prefix, adapter):
            pass

        def get(self, url, params=None, timeout=None):
            return SimpleNamespace(
                status_code=200,
                headers={"X-Request-Id": "rid"},
                request=SimpleNamespace(headers=self.headers),
                url=url,
                json=lambda: [],
                raise_for_status=lambda: None,
            )

    sleep_called = {"v": 0.0}

    def fake_sleep(seconds):
        sleep_called["v"] = seconds

    counter = {"v": 0.0}

    def fake_perf_counter() -> float:
        counter["v"] += 0.001
        return counter["v"]

    monkeypatch.setattr(time, "perf_counter", fake_perf_counter)
    monkeypatch.setattr(time, "sleep", fake_sleep)

    client = CoinGeckoClient(api_key="demo-key", plan="demo", session=DummySession())

    with caplog.at_level("INFO", logger="backend.app.services.coingecko"):
        client.get_markets()

    assert sleep_called["v"] >= 2.1
    record = next(r for r in caplog.records if r.message.startswith("{"))
    data = json.loads(record.message)
    assert data["url"].endswith("/coins/markets")
    assert data["status"] == 200
    assert data["plan"] == "demo"
    assert data["sent_demo_header"] is True


def test_coingecko_client_linear_backoff_on_429(monkeypatch):
    from backend.app.core import settings as settings_module
    from backend.app.services.coingecko import CoinGeckoClient

    monkeypatch.setattr(settings_module.settings, "CG_THROTTLE_MS", 150)

    class DummyResp:
        def __init__(self, status_code: int, payload: list):
            self.status_code = status_code
            self._payload = payload
            self.headers = {"X-Request-Id": "rid"}
            self.url = "https://api.coingecko.com/api/v3/coins/markets"
            self.request = type("Req", (), {"headers": {}})()

        def json(self):
            return self._payload

        def raise_for_status(self):
            if self.status_code >= 400:
                raise requests.HTTPError(response=self)

    class DummySession:
        def __init__(self) -> None:
            self.headers: dict = {}
            self.calls = 0

        def mount(self, prefix, adapter):
            pass

        def get(self, url, params=None, timeout=None):
            self.calls += 1
            if self.calls == 1:
                return DummyResp(429, [])
            return DummyResp(200, ["ok"])

    sleep_calls: list[float] = []
    current_time = {"v": 0.0}

    def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)
        current_time["v"] += seconds

    def fake_monotonic() -> float:
        return current_time["v"]

    monkeypatch.setattr(time, "sleep", fake_sleep)
    monkeypatch.setattr(time, "monotonic", fake_monotonic)

    client = CoinGeckoClient(api_key=None, plan="pro", session=DummySession())
    result = client.get_markets()

    assert result == ["ok"]
    assert len(sleep_calls) == 2
    assert sleep_calls[-1] == pytest.approx(0.15, rel=1e-6)
    assert client.session.calls == 2
