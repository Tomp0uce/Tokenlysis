from subprocess import CompletedProcess
import importlib

import backend.app.core.settings as settings_module
import backend.app.services.coingecko as coingecko
import backend.app.main as main_module
from fastapi.testclient import TestClient


def test_debug_endpoint(monkeypatch):
    monkeypatch.setenv("COINGECKO_API_KEY", "test-key")
    importlib.reload(settings_module)
    importlib.reload(coingecko)
    importlib.reload(main_module)
    client = TestClient(main_module.app)

    def fake_run(cmd, capture_output, text):
        return CompletedProcess(cmd, 0, stdout="pong", stderr="")

    monkeypatch.setattr("backend.app.debug.run", fake_run)

    resp = client.get("/api/debug")
    assert resp.status_code == 200
    data = resp.json()
    assert data["api_key"] == "test-key"
    assert "coins/markets" in data["coingecko_command"]
    assert data["ping_response"] == "pong"
