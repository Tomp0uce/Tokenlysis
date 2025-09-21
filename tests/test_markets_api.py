import logging

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.core.settings import settings
from backend.app.db import Base, get_session
from backend.app.services.dao import PricesRepo


def _setup_test_session(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path/'test.db'}", connect_args={"check_same_thread": False}
    )
    TestingSessionLocal = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
    )
    Base.metadata.create_all(bind=engine)
    return TestingSessionLocal


def test_markets_top_limit_bound_and_logging(monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(settings, "CG_TOP_N", 100)
    TestingSessionLocal = _setup_test_session(tmp_path)
    import backend.app.main as main_module

    monkeypatch.setattr(main_module.settings, "CG_TOP_N", 100)

    main_module.app.dependency_overrides[get_session] = lambda: TestingSessionLocal()

    called_limits: list[int] = []

    def _get_top(self, vs: str, limit: int):
        called_limits.append(limit)
        return []

    monkeypatch.setattr(PricesRepo, "get_top", _get_top)
    client = TestClient(main_module.app)

    caplog.clear()
    with caplog.at_level(logging.INFO, logger="backend.app.main"):
        resp = client.get("/api/markets/top?limit=500&vs=usd")
    assert resp.status_code == 200
    assert called_limits[-1] == 100
    assert not caplog.records

    caplog.clear()
    with caplog.at_level(logging.DEBUG, logger="backend.app.main"):
        resp = client.get("/api/markets/top?limit=500&vs=usd")
    assert resp.status_code == 200
    assert called_limits[-1] == 100
    debug_record = caplog.records[-1]
    assert debug_record.levelno == logging.DEBUG
    assert debug_record.limit_effective == 100
    assert debug_record.vs == "usd"

    caplog.clear()
    with caplog.at_level(logging.DEBUG, logger="backend.app.main"):
        resp = client.get("/api/markets/top?limit=0&vs=usd")
    assert resp.status_code == 200
    assert called_limits[-1] == 1
    debug_record = caplog.records[-1]
    assert debug_record.levelno == logging.DEBUG
    assert debug_record.limit_effective == 1
    assert debug_record.vs == "usd"


def test_markets_top_invalid_vs(monkeypatch, tmp_path):
    TestingSessionLocal = _setup_test_session(tmp_path)
    import backend.app.main as main_module

    main_module.app.dependency_overrides[get_session] = lambda: TestingSessionLocal()
    client = TestClient(main_module.app)

    resp = client.get("/api/markets/top?limit=1&vs=eur")
    assert resp.status_code == 400


def test_frontend_routes_emit_no_warnings(monkeypatch, tmp_path, caplog):
    TestingSessionLocal = _setup_test_session(tmp_path)

    def _session_override():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    import backend.app.main as main_module

    monkeypatch.setattr(main_module.logging, "basicConfig", lambda **_k: None)
    monkeypatch.setattr(main_module, "get_session", _session_override)

    async def _noop_async(*_a, **_k):
        return 0

    monkeypatch.setattr(main_module, "run_etl_async", _noop_async)
    monkeypatch.setattr(main_module, "sync_fear_greed_async", _noop_async)
    monkeypatch.setattr(main_module, "load_seed", lambda *_a, **_k: None)

    caplog.clear()
    caplog.set_level(logging.WARNING)

    with caplog.at_level(logging.WARNING):
        with TestClient(main_module.app) as client:
            response = client.get("/")
    assert response.status_code == 200
    warning_records = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert warning_records == []
