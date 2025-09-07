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

    with caplog.at_level(logging.INFO, logger="backend.app.main"):
        resp = client.get("/api/markets/top?limit=500&vs=usd")
    assert resp.status_code == 200
    assert called_limits[-1] == 100
    record = caplog.records[-1]
    assert record.limit_effective == 100
    assert record.vs == "usd"

    with caplog.at_level(logging.INFO, logger="backend.app.main"):
        resp = client.get("/api/markets/top?limit=0&vs=usd")
    assert resp.status_code == 200
    assert called_limits[-1] == 1
    record = caplog.records[-1]
    assert record.limit_effective == 1
    assert record.vs == "usd"


def test_markets_top_invalid_vs(monkeypatch, tmp_path):
    TestingSessionLocal = _setup_test_session(tmp_path)
    import backend.app.main as main_module

    main_module.app.dependency_overrides[get_session] = lambda: TestingSessionLocal()
    client = TestClient(main_module.app)

    resp = client.get("/api/markets/top?limit=1&vs=eur")
    assert resp.status_code == 400
