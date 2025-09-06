from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import app


def test_root_serves_index_html() -> None:
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    index_file = Path(__file__).resolve().parents[1] / "frontend" / "index.html"
    assert response.text == index_file.read_text()
