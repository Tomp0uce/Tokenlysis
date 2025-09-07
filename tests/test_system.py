from importlib import reload

import backend.app.core.settings as settings_module
from fastapi.testclient import TestClient


def test_health_and_ready(monkeypatch):
    import backend.app.main as main_module

    monkeypatch.setattr(main_module.CoinGeckoClient, "ping", lambda self: "pong")
    client = TestClient(main_module.app)
    assert client.get("/healthz").status_code == 200
    assert client.get("/readyz").status_code == 200


def test_readyz_failure(monkeypatch):
    import backend.app.main as main_module

    client = TestClient(main_module.app)
    assert client.get("/readyz").status_code == 200


def test_diag_masks_key(monkeypatch):
    monkeypatch.setenv("COINGECKO_API_KEY", "supersecret1234")
    reload(settings_module)
    import backend.app.main as main_module

    reload(main_module)
    monkeypatch.setattr(main_module.CoinGeckoClient, "ping", lambda self: "pong")
    client = TestClient(main_module.app)
    resp = client.get("/api/diag")
    assert resp.status_code == 200
    data = resp.json()
    assert data["api_key_masked"].endswith("1234")
    assert "supersecret1234" not in resp.text
