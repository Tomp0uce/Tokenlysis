from backend.app.core.version import get_version
from backend.app.main import app
from fastapi.testclient import TestClient


def test_version_endpoint() -> None:
    client = TestClient(app)
    expected = get_version()
    response = client.get("/api/version")
    assert response.status_code == 200
    assert response.json() == {"version": expected}
