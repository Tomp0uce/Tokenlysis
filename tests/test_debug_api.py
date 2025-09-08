import time

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.db import Base


def _setup_test_session(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path/'test.db'}", connect_args={"check_same_thread": False}
    )
    TestingSessionLocal = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
    )
    Base.metadata.create_all(bind=engine)
    return TestingSessionLocal


def test_last_request_endpoint(monkeypatch, tmp_path):
    import backend.app.main as main_module
    from backend.app.services import coingecko as cg_module

    TestingSessionLocal = _setup_test_session(tmp_path)
    monkeypatch.setattr(cg_module, "SessionLocal", TestingSessionLocal)

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

    monkeypatch.setattr(time, "sleep", lambda s: None)
    monkeypatch.setattr(main_module, "run_etl", lambda *_, **__: None)
    monkeypatch.setattr(main_module, "load_seed", lambda *_, **__: None)

    client = cg_module.CoinGeckoClient(api_key=None, session=DummySession())
    with TestClient(main_module.app) as tc:
        client.get_markets()
        resp = tc.get("/api/debug/last-request")
    assert resp.status_code == 200
    data = resp.json()
    assert data["endpoint"] == "/coins/markets"
    assert data["status"] == 200


def test_last_request_persisted(monkeypatch, tmp_path):
    import backend.app.main as main_module
    from backend.app.services import coingecko as cg_module

    TestingSessionLocal = _setup_test_session(tmp_path)
    monkeypatch.setattr(cg_module, "SessionLocal", TestingSessionLocal)

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

    monkeypatch.setattr(time, "sleep", lambda s: None)
    monkeypatch.setattr(main_module, "run_etl", lambda *_, **__: None)
    monkeypatch.setattr(main_module, "load_seed", lambda *_, **__: None)

    client = cg_module.CoinGeckoClient(api_key=None, session=DummySession())
    client.get_markets()

    # simulate restart by clearing in-memory cache
    cg_module.last_request = None

    with TestClient(main_module.app) as tc:
        resp = tc.get("/api/debug/last-request")
    data = resp.json()
    assert data["endpoint"] == "/coins/markets"
    assert data["status"] == 200
