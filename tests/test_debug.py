from subprocess import CompletedProcess

from backend.app.main import app
from fastapi.testclient import TestClient


def test_debug_endpoint(monkeypatch):
    client = TestClient(app)

    def fake_run(cmd, capture_output, text):
        return CompletedProcess(cmd, 0, stdout="pong", stderr="")

    monkeypatch.setenv("COINGECKO_API_KEY", "test-key")
    monkeypatch.setattr("backend.app.debug.run", fake_run)

    resp = client.get("/api/debug")
    assert resp.status_code == 200
    data = resp.json()
    assert data["api_key"] == "test-key"
    assert "coins/markets" in data["coingecko_command"]
    assert data["ping_response"] == "pong"
