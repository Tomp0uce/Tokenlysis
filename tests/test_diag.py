import datetime as dt

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.core.settings import settings
from backend.app.core.settings import effective_coingecko_base_url
from backend.app.db import Base, get_session
from backend.app.services.dao import MetaRepo, FearGreedRepo
from backend.app.services.budget import CallBudget


def _setup_test_session(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path/'test.db'}", connect_args={"check_same_thread": False}
    )
    TestingSessionLocal = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
    )
    Base.metadata.create_all(bind=engine)
    return TestingSessionLocal


def test_diag_returns_debug(monkeypatch, tmp_path):
    TestingSessionLocal = _setup_test_session(tmp_path)
    session = TestingSessionLocal()
    meta = MetaRepo(session)
    meta.set("last_refresh_at", "2025-09-07T20:51:26Z")
    meta.set("last_etl_items", "50")
    meta.set("data_source", "api")
    meta.set("monthly_call_count", "999")
    session.commit()
    session.close()

    budget = CallBudget(tmp_path / "budget.json", quota=settings.CG_MONTHLY_QUOTA)
    budget.spend(2)

    import backend.app.main as main_module

    main_module.app.dependency_overrides[get_session] = lambda: TestingSessionLocal()
    main_module.app.state.budget = budget

    client = TestClient(main_module.app)
    resp = client.get("/api/diag")
    assert resp.status_code == 200
    data = resp.json()
    assert data["plan"] == settings.COINGECKO_PLAN
    assert data["base_url"] == effective_coingecko_base_url()
    assert data["granularity"] == "12h"
    assert data["last_refresh_at"] == "2025-09-07T20:51:26Z"
    assert data["last_etl_items"] == 50
    assert data["monthly_call_count"] == 2
    assert data["quota"] == settings.CG_MONTHLY_QUOTA
    assert data["data_source"] == "api"
    assert data["top_n"] == settings.CG_TOP_N
    assert data["fear_greed_last_refresh"] is None
    assert data["fear_greed_count"] == 0


def test_diag_uses_budget_over_meta(monkeypatch, tmp_path):
    TestingSessionLocal = _setup_test_session(tmp_path)
    session = TestingSessionLocal()
    MetaRepo(session).set("monthly_call_count", "999")
    session.commit()
    session.close()

    budget = CallBudget(tmp_path / "budget.json", quota=settings.CG_MONTHLY_QUOTA)
    budget.spend(3)

    import backend.app.main as main_module

    main_module.app.dependency_overrides[get_session] = lambda: TestingSessionLocal()
    main_module.app.state.budget = budget

    client = TestClient(main_module.app)
    resp = client.get("/api/diag")
    data = resp.json()
    assert data["monthly_call_count"] == 3


def test_diag_no_budget(monkeypatch, tmp_path):
    TestingSessionLocal = _setup_test_session(tmp_path)
    import backend.app.main as main_module

    main_module.app.dependency_overrides[get_session] = lambda: TestingSessionLocal()
    main_module.app.state.budget = None

    client = TestClient(main_module.app)
    resp = client.get("/api/diag")
    data = resp.json()
    assert data["monthly_call_count"] == 0
    assert data["last_refresh_at"] is None
    assert data["last_etl_items"] == 0
    assert data["data_source"] is None
    assert data["fear_greed_last_refresh"] is None
    assert data["fear_greed_count"] == 0


def test_diag_handles_invalid_last_etl_items(monkeypatch, tmp_path):
    TestingSessionLocal = _setup_test_session(tmp_path)
    session = TestingSessionLocal()
    MetaRepo(session).set("last_etl_items", "oops")
    session.commit()
    session.close()

    import backend.app.main as main_module

    main_module.app.dependency_overrides[get_session] = lambda: TestingSessionLocal()
    main_module.app.state.budget = None

    client = TestClient(main_module.app)
    resp = client.get("/api/diag")
    data = resp.json()
    assert data["last_etl_items"] == 0


def test_diag_reports_fear_greed_metrics(monkeypatch, tmp_path):
    TestingSessionLocal = _setup_test_session(tmp_path)
    session = TestingSessionLocal()
    repo = FearGreedRepo(session)
    now = dt.datetime(2025, 1, 2, tzinfo=dt.timezone.utc)
    earlier = now - dt.timedelta(days=1)
    repo.upsert_many(
        [
            {
                "timestamp": earlier,
                "value": 20,
                "classification": "Fear",
                "ingested_at": now,
            },
            {
                "timestamp": now,
                "value": 55,
                "classification": "Greed",
                "ingested_at": now,
            },
        ]
    )
    meta = MetaRepo(session)
    meta.set("fear_greed_last_refresh", now.isoformat())
    session.commit()
    session.close()

    import backend.app.main as main_module

    main_module.app.dependency_overrides[get_session] = lambda: TestingSessionLocal()
    main_module.app.state.budget = None

    client = TestClient(main_module.app)
    resp = client.get("/api/diag")
    assert resp.status_code == 200
    data = resp.json()
    assert data["fear_greed_last_refresh"] == now.isoformat()
    assert data["fear_greed_count"] == 2


def test_diag_uses_configurable_granularity(monkeypatch, tmp_path):
    TestingSessionLocal = _setup_test_session(tmp_path)
    import backend.app.main as main_module

    monkeypatch.setattr(main_module.settings, "REFRESH_GRANULARITY", "1h")
    main_module.app.dependency_overrides[get_session] = lambda: TestingSessionLocal()
    main_module.app.state.budget = None

    client = TestClient(main_module.app)
    resp = client.get("/api/diag")
    data = resp.json()
    assert data["granularity"] == "1h"
