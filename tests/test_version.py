from backend.app.core.version import get_version
from backend.app.main import app
from fastapi.testclient import TestClient
from typing import Any
import backend.app.core.version as version_module


def test_version_endpoint() -> None:
    client = TestClient(app)
    expected = get_version()
    response = client.get("/api/version")
    assert response.status_code == 200
    assert response.json() == {"version": expected}


def test_get_version_env_fallback(monkeypatch) -> None:
    """Ensure environment variable is used when git command fails."""
    monkeypatch.setenv("APP_VERSION", "123")

    def _raise(*args: Any, **kwargs: Any) -> bytes:
        raise FileNotFoundError

    monkeypatch.setattr(version_module, "check_output", _raise)
    assert version_module.get_version() == "123"
