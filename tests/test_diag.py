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
    budget.spend(1, category="markets")
    budget.spend(1, category="coin_profile")

    import backend.app.main as main_module

    main_module.app.dependency_overrides[get_session] = lambda: TestingSessionLocal()
    main_module.app.state.budget = budget
    main_module.app.state.cmc_budget = None

    client = TestClient(main_module.app)
    resp = client.get("/api/diag")
    assert resp.status_code == 200
    data = resp.json()
    providers = data["providers"]
    cmc_provider = providers["coinmarketcap"]
    cg_provider = providers["coingecko"]
    assert cmc_provider["base_url"].startswith("https://")
    assert cmc_provider["fng_latest"]["path"] == "/v3/fear-and-greed/latest"
    assert cmc_provider["fng_latest"]["safe_url"].endswith(
        "/v3/fear-and-greed/latest"
    )
    assert cmc_provider["fng_historical"]["path"] == "/v3/fear-and-greed/historical"
    assert cmc_provider["api_key_masked"] == ""
    assert "doc_url" in cmc_provider["fng_latest"]

    assert cg_provider["base_url"] == effective_coingecko_base_url()
    assert cg_provider["markets"]["path"] == "/coins/markets"
    assert cg_provider["markets"]["safe_url"].endswith("/coins/markets?vs_currency=usd")
    assert "doc_url" in cg_provider["markets"]

    etl = data["etl"]
    assert etl["granularity"] == "12h"
    assert etl["last_refresh_at"] == "2025-09-07T20:51:26Z"
    assert etl["last_etl_items"] == 50
    assert etl["top_n"] == settings.CG_TOP_N
    assert etl["data_source"] == "api"

    cg_usage = data["coingecko_usage"]
    assert cg_usage["plan"] == settings.COINGECKO_PLAN
    assert cg_usage["monthly_call_count"] == 2
    assert cg_usage["monthly_call_categories"] == {
        "coin_profile": 1,
        "markets": 1,
    }
    assert cg_usage["quota"] == settings.CG_MONTHLY_QUOTA

    cmc_usage = data["coinmarketcap_usage"]
    assert cmc_usage["monthly_call_count"] == 0
    assert cmc_usage["monthly_call_categories"] == {}

    fng_cache = data["fng_cache"]
    assert fng_cache["rows"] == 0
    assert fng_cache["last_refresh"] is None
    assert fng_cache["min_timestamp"] is None
    assert fng_cache["max_timestamp"] is None


def test_diag_uses_budget_over_meta(monkeypatch, tmp_path):
    TestingSessionLocal = _setup_test_session(tmp_path)
    session = TestingSessionLocal()
    MetaRepo(session).set("monthly_call_count", "999")
    session.commit()
    session.close()

    budget = CallBudget(tmp_path / "budget.json", quota=settings.CG_MONTHLY_QUOTA)
    budget.spend(3, category="markets")

    import backend.app.main as main_module

    main_module.app.dependency_overrides[get_session] = lambda: TestingSessionLocal()
    main_module.app.state.budget = budget
    main_module.app.state.cmc_budget = None

    client = TestClient(main_module.app)
    resp = client.get("/api/diag")
    data = resp.json()
    assert data["coingecko_usage"]["monthly_call_count"] == 3
    assert data["coingecko_usage"]["monthly_call_categories"] == {"markets": 3}


def test_diag_no_budget(monkeypatch, tmp_path):
    TestingSessionLocal = _setup_test_session(tmp_path)
    import backend.app.main as main_module

    main_module.app.dependency_overrides[get_session] = lambda: TestingSessionLocal()
    main_module.app.state.budget = None
    main_module.app.state.cmc_budget = None

    client = TestClient(main_module.app)
    resp = client.get("/api/diag")
    data = resp.json()
    assert data["coingecko_usage"]["monthly_call_count"] == 0
    assert data["coingecko_usage"]["monthly_call_categories"] == {}
    assert data["etl"]["last_refresh_at"] is None
    assert data["etl"]["last_etl_items"] == 0
    assert data["etl"]["data_source"] is None
    assert data["fng_cache"]["last_refresh"] is None
    assert data["fng_cache"]["rows"] == 0


def test_diag_handles_invalid_last_etl_items(monkeypatch, tmp_path):
    TestingSessionLocal = _setup_test_session(tmp_path)
    session = TestingSessionLocal()
    MetaRepo(session).set("last_etl_items", "oops")
    session.commit()
    session.close()

    import backend.app.main as main_module

    main_module.app.dependency_overrides[get_session] = lambda: TestingSessionLocal()
    main_module.app.state.budget = None
    main_module.app.state.cmc_budget = None

    client = TestClient(main_module.app)
    resp = client.get("/api/diag")
    data = resp.json()
    assert data["etl"]["last_etl_items"] == 0


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
    main_module.app.state.cmc_budget = None

    client = TestClient(main_module.app)
    resp = client.get("/api/diag")
    assert resp.status_code == 200
    data = resp.json()
    expected_refresh = now.isoformat().replace("+00:00", "Z")
    assert data["fng_cache"]["last_refresh"] == expected_refresh
    assert data["fng_cache"]["rows"] == 2
    assert data["fng_cache"]["min_timestamp"].startswith("2025-01-01")
    assert data["fng_cache"]["max_timestamp"].startswith("2025-01-02")


def test_diag_uses_configurable_granularity(monkeypatch, tmp_path):
    TestingSessionLocal = _setup_test_session(tmp_path)
    import backend.app.main as main_module

    monkeypatch.setattr(main_module.settings, "REFRESH_GRANULARITY", "1h")
    main_module.app.dependency_overrides[get_session] = lambda: TestingSessionLocal()
    main_module.app.state.budget = None
    main_module.app.state.cmc_budget = None


def test_diag_reports_cmc_budget(monkeypatch, tmp_path):
    TestingSessionLocal = _setup_test_session(tmp_path)
    import backend.app.main as main_module
    from backend.app.core.settings import settings

    cmc_budget = CallBudget(tmp_path / "cmc_budget.json", quota=5)
    cmc_budget.spend(2, category="cmc_history")
    cmc_budget.spend(1, category="cmc_latest")

    monkeypatch.setattr(settings, "CMC_MONTHLY_QUOTA", 5)
    monkeypatch.setattr(settings, "CMC_ALERT_THRESHOLD", 0.8)
    main_module.app.dependency_overrides[get_session] = lambda: TestingSessionLocal()
    main_module.app.state.budget = None
    main_module.app.state.cmc_budget = cmc_budget

    client = TestClient(main_module.app)
    resp = client.get("/api/diag")
    assert resp.status_code == 200
    data = resp.json()
    assert data["coinmarketcap_usage"]["monthly_call_count"] == 3
    assert data["coinmarketcap_usage"]["monthly_call_categories"] == {
        "cmc_history": 2,
        "cmc_latest": 1,
    }
    assert data["coinmarketcap_usage"]["quota"] == 5
    assert data["coinmarketcap_usage"]["alert_threshold"] == 0.8

    main_module.app.state.cmc_budget = None

