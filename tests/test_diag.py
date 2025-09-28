import datetime as dt
import json

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
import requests
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
    cg_reset = dt.datetime.fromisoformat(cg_usage["reset_at"].replace("Z", "+00:00"))
    assert cg_reset.day == 1

    cmc_usage = data["coinmarketcap_usage"]
    assert cmc_usage["monthly_call_count"] == 0
    assert cmc_usage["monthly_call_categories"] == {}
    cmc_reset = dt.datetime.fromisoformat(cmc_usage["reset_at"].replace("Z", "+00:00"))
    assert cmc_reset.day == 1

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


def test_fetch_cmc_usage_parses_real_payload(monkeypatch):
    import backend.app.main as main_module

    sample_payload = {
        "status": {
            "timestamp": "2025-09-28T10:21:04.716Z",
            "error_code": 0,
            "error_message": None,
            "elapsed": 5,
            "credit_count": 0,
            "notice": None,
        },
        "data": {
            "plan": {
                "credit_limit_monthly": 10000,
                "credit_limit_monthly_reset": "In 2 days, 13 hours, 38 minutes",
                "credit_limit_monthly_reset_timestamp": "2025-10-01T00:00:00.000Z",
                "rate_limit_minute": 30,
            },
            "usage": {
                "current_minute": {"requests_made": 0, "requests_left": 30},
                "current_day": {"credits_used": 18},
                "current_month": {"credits_used": 239, "credits_left": 9761},
            },
        },
    }

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return sample_payload

    captured: dict[str, object] = {}

    def fake_get(url: str, *, headers=None, timeout=None, **kwargs):
        captured.update({
            "url": url,
            "headers": headers,
            "timeout": timeout,
            "kwargs": kwargs,
        })
        return FakeResponse()

    monkeypatch.setattr(main_module.requests, "get", fake_get)

    result = main_module._fetch_cmc_usage("cmc-test-key")

    assert captured["url"] == "https://pro-api.coinmarketcap.com/v1/key/info"
    assert captured["headers"]["X-CMC_PRO_API_KEY"] == "cmc-test-key"
    assert captured["headers"]["Accept"] == "application/json"
    assert captured["kwargs"].get("params") is None
    assert result["monthly_call_count"] == 239
    assert result["quota"] == 10000
    assert result["remaining"] == 9761
    assert result["monthly"]["credits_used"] == 239
    assert result["monthly"]["credits_left"] == 9761


def test_refresh_usage_fetches_provider_stats(monkeypatch, tmp_path):
    import backend.app.main as main_module

    monkeypatch.setattr(main_module.settings, "COINGECKO_PLAN", "pro")
    monkeypatch.setattr(main_module.settings, "COINGECKO_API_KEY", "cg-live-1234")
    monkeypatch.setattr(main_module.settings, "coingecko_api_key", None)
    monkeypatch.setattr(main_module.settings, "CMC_API_KEY", "cmc-live-5678")
    main_module.app.state.usage_cache = None

    calls: list[tuple[str, dict[str, str] | None, float | None, dict[str, object]]] = []

    class FakeResponse:
        def __init__(self, payload: dict[str, object]) -> None:
            self._payload = payload

        def raise_for_status(self) -> None:  # pragma: no cover - interface stub
            return None

        def json(self) -> dict[str, object]:
            return self._payload

    def fake_get(url: str, *, headers=None, timeout=None, **kwargs):
        calls.append((url, headers, timeout, kwargs))
        if "coinmarketcap" in url:
            return FakeResponse(
                {
                    "data": {
                        "plan": {"credit_limit_monthly": 5000},
                        "usage": {
                            "current_month": {
                                "credits_used": 320,
                                "credits_left": 4680,
                                "quota": 5000,
                            }
                        },
                    }
                }
            )
        raise AssertionError(f"Unexpected URL {url}")

    monkeypatch.setattr(main_module.requests, "get", fake_get)

    cg_budget = CallBudget(tmp_path / "cg-live.json", quota=1000)
    cg_budget.spend(120, category="markets")
    main_module.app.state.budget = cg_budget
    main_module.app.state.cmc_budget = CallBudget(tmp_path / "cmc-live.json", quota=5000)

    client = TestClient(main_module.app)
    response = client.post("/api/diag/refresh-usage")
    assert response.status_code == 200
    payload = response.json()

    assert payload["coingecko"]["monthly_call_count"] == 120
    assert payload["coingecko"]["quota"] == settings.CG_MONTHLY_QUOTA
    assert payload["coingecko"]["monthly_call_categories"] == {"markets": 120}
    assert payload["coinmarketcap"]["monthly_call_count"] == 320
    assert payload["coinmarketcap"]["quota"] == 5000

    assert len(calls) == 1
    cmc_call = calls[0]
    assert "coinmarketcap" in cmc_call[0]
    assert cmc_call[1]["X-CMC_PRO_API_KEY"] == "cmc-live-5678"
    assert cmc_call[1].get("Accept") == "application/json"
    assert cmc_call[3].get("params") is None
    assert cmc_call[2] == 10


def test_refresh_usage_requires_api_keys(monkeypatch):
    import backend.app.main as main_module

    monkeypatch.setattr(main_module.settings, "COINGECKO_API_KEY", None)
    monkeypatch.setattr(main_module.settings, "coingecko_api_key", None)
    monkeypatch.setattr(main_module.settings, "CMC_API_KEY", None)
    main_module.app.state.usage_cache = None

    client = TestClient(main_module.app)
    response = client.post("/api/diag/refresh-usage")
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "CoinGecko" in detail
    assert "CoinMarketCap" in detail


def test_refresh_usage_uses_cache(monkeypatch, tmp_path):
    import backend.app.main as main_module

    monkeypatch.setattr(main_module.settings, "COINGECKO_API_KEY", "cg-cache-1")
    monkeypatch.setattr(main_module.settings, "coingecko_api_key", None)
    monkeypatch.setattr(main_module.settings, "CMC_API_KEY", "cmc-cache-1")
    main_module.app.state.usage_cache = None

    class FakeResponse:
        def __init__(self, payload: dict[str, object]) -> None:
            self._payload = payload

        def raise_for_status(self) -> None:  # pragma: no cover - interface stub
            return None

        def json(self) -> dict[str, object]:
            return self._payload

    cmc_calls = 0

    def fake_get(url: str, *, headers=None, timeout=None, **kwargs):
        nonlocal cmc_calls
        if "coinmarketcap" in url:
            cmc_calls += 1
            return FakeResponse(
                {
                    "data": {
                        "plan": {"credit_limit_monthly": 5000},
                        "usage": {
                            "current_month": {
                                "credits_used": 320,
                                "credits_left": 4680,
                                "quota": 5000,
                            }
                        },
                    }
                }
            )
        raise AssertionError(f"Unexpected URL {url}")

    monkeypatch.setattr(main_module.requests, "get", fake_get)

    cg_budget = CallBudget(tmp_path / "cg-cache.json", quota=1000)
    cg_budget.spend(120, category="markets")
    main_module.app.state.budget = cg_budget

    client = TestClient(main_module.app)
    first = client.post("/api/diag/refresh-usage")
    assert first.status_code == 200
    second = client.post("/api/diag/refresh-usage")
    assert second.status_code == 200

    assert first.json() == second.json()
    assert cmc_calls == 1

    payload = first.json()
    cg_usage = payload["coingecko"]
    assert cg_usage["monthly_call_count"] == 120
    assert cg_usage["monthly_call_categories"] == {"markets": 120}
    reset_at = dt.datetime.fromisoformat(cg_usage["reset_at"].replace("Z", "+00:00"))
    assert reset_at.day == 1


def test_refresh_usage_cache_expires(monkeypatch, tmp_path):
    import backend.app.main as main_module

    monkeypatch.setattr(main_module.settings, "COINGECKO_API_KEY", "cg-cache-2")
    monkeypatch.setattr(main_module.settings, "coingecko_api_key", None)
    monkeypatch.setattr(main_module.settings, "CMC_API_KEY", "cmc-cache-2")
    main_module.app.state.usage_cache = None

    class FakeResponse:
        def __init__(self, payload: dict[str, object]) -> None:
            self._payload = payload

        def raise_for_status(self) -> None:  # pragma: no cover - interface stub
            return None

        def json(self) -> dict[str, object]:
            return self._payload

    cmc_payloads = [
        {
            "data": {
                "plan": {"credit_limit_monthly": 5000},
                "usage": {
                    "current_month": {
                        "credits_used": 320,
                        "credits_left": 4680,
                        "quota": 5000,
                    }
                },
            }
        },
        {
            "data": {
                "plan": {"credit_limit_monthly": 7000},
                "usage": {
                    "current_month": {
                        "credits_used": 540,
                        "credits_left": 6460,
                        "quota": 7000,
                    }
                },
            }
        },
    ]

    def fake_get(url: str, *, headers=None, timeout=None, **kwargs):
        if "coinmarketcap" in url:
            payload = cmc_payloads.pop(0)
            return FakeResponse(payload)
        raise AssertionError(f"Unexpected URL {url}")

    monkeypatch.setattr(main_module.requests, "get", fake_get)

    cg_budget = CallBudget(tmp_path / "cg-cache-expire.json", quota=2000)
    cg_budget.spend(120, category="markets")
    main_module.app.state.budget = cg_budget

    class FakeDateTime(dt.datetime):
        slots: list[dt.datetime] = []

        @classmethod
        def now(cls, tz=None):
            if not cls.slots:
                raise AssertionError("FakeDateTime.now called too many times")
            value = cls.slots.pop(0)
            if tz is None:
                return value
            return value.astimezone(tz)

    start = dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc)
    later = start + dt.timedelta(seconds=main_module.USAGE_CACHE_TTL_SECONDS + 1)
    FakeDateTime.slots = [start, later]

    monkeypatch.setattr(main_module.dt, "datetime", FakeDateTime)

    client = TestClient(main_module.app)
    first = client.post("/api/diag/refresh-usage")
    assert first.status_code == 200
    second = client.post("/api/diag/refresh-usage")
    assert second.status_code == 200

    assert first.json() != second.json()
    assert first.json()["coingecko"]["monthly_call_count"] == 120
    assert second.json()["coingecko"]["monthly_call_count"] == 120
    assert first.json()["coinmarketcap"]["monthly_call_count"] == 320
    assert second.json()["coinmarketcap"]["monthly_call_count"] == 540


def test_refresh_usage_recovers_from_coingecko_plan_mismatch(monkeypatch, tmp_path):
    import backend.app.main as main_module

    monkeypatch.setattr(main_module.settings, "COINGECKO_PLAN", "demo")
    monkeypatch.setattr(main_module.settings, "COINGECKO_API_KEY", "cg-mismatch")
    monkeypatch.setattr(main_module.settings, "coingecko_api_key", None)
    monkeypatch.setattr(main_module.settings, "CMC_API_KEY", "cmc-ok")
    main_module.app.state.usage_cache = None

    class FakeResponse:
        def __init__(self, payload: dict[str, object], status_code: int) -> None:
            self._payload = payload
            self.status_code = status_code

        def raise_for_status(self) -> None:  # pragma: no cover - interface stub
            if self.status_code >= 400:
                error = requests.HTTPError(f"HTTP {self.status_code}")
                error.response = self  # type: ignore[attr-defined]
                raise error

        def json(self) -> dict[str, object]:
            return self._payload

    attempts: list[str] = []

    def fake_get(url: str, *, headers=None, timeout=None, **kwargs):
        if "coingecko" in url:
            attempts.append(url)
            raise AssertionError("CoinGecko endpoint should not be called")
        if "coinmarketcap" in url:
            return FakeResponse(
                {
                    "data": {
                        "plan": {"credit_limit_monthly": 5000},
                        "usage": {
                            "current_month": {
                                "credits_used": 320,
                                "credits_left": 4680,
                                "quota": 5000,
                            }
                        },
                    }
                },
                200,
            )
        raise AssertionError(f"Unexpected URL {url}")

    monkeypatch.setattr(main_module.requests, "get", fake_get)

    cg_budget = CallBudget(tmp_path / "cg-mismatch.json", quota=1000)
    cg_budget.spend(200, category="markets")
    main_module.app.state.budget = cg_budget

    client = TestClient(main_module.app)
    response = client.post("/api/diag/refresh-usage")
    assert response.status_code == 200
    assert attempts == []


def test_refresh_usage_uses_budget_snapshot(monkeypatch, tmp_path):
    import backend.app.main as main_module

    monkeypatch.setattr(main_module.settings, "COINGECKO_PLAN", "demo")
    monkeypatch.setattr(main_module.settings, "COINGECKO_API_KEY", "cg-key")
    monkeypatch.setattr(main_module.settings, "coingecko_api_key", None)
    monkeypatch.setattr(main_module.settings, "CMC_API_KEY", "cmc-key")
    main_module.app.state.usage_cache = None

    cg_budget_path = tmp_path / "cg_budget.json"
    cmc_budget_path = tmp_path / "cmc_budget.json"
    cg_budget = CallBudget(cg_budget_path, quota=1000)
    cg_budget.spend(120, category="markets")
    cg_budget.spend(20, category="coin_profile")
    main_module.app.state.budget = cg_budget
    main_module.app.state.cmc_budget = CallBudget(cmc_budget_path, quota=5000)

    class FakeResponse:
        def __init__(self, payload: dict[str, object], status_code: int) -> None:
            self._payload = payload
            self.status_code = status_code

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                error = requests.HTTPError(f"HTTP {self.status_code}")
                error.response = self  # type: ignore[attr-defined]
                raise error

        def json(self) -> dict[str, object]:
            return self._payload

    requested_urls: list[str] = []

    def fake_get(url: str, *, headers=None, params=None, timeout=None, **kwargs):
        requested_urls.append(url)
        if "coinmarketcap" in url:
            assert headers.get("X-CMC_PRO_API_KEY") == "cmc-key"
            return FakeResponse(
                {
                    "data": {
                        "plan": {"credit_limit_monthly": 5000},
                        "usage": {
                            "current_month": {
                                "credits_used": 320,
                                "credits_left": 4680,
                            }
                        },
                    }
                },
                200,
            )
        raise AssertionError(f"Unexpected URL {url}")

    monkeypatch.setattr(main_module.requests, "get", fake_get)

    client = TestClient(main_module.app)
    response = client.post("/api/diag/refresh-usage")

    assert response.status_code == 200
    assert requested_urls == ["https://pro-api.coinmarketcap.com/v1/key/info"]

    assert main_module.app.state.budget.monthly_call_count == 140
    assert main_module.app.state.cmc_budget.monthly_call_count == 320

    cg_payload = json.loads(cg_budget_path.read_text())
    cmc_payload = json.loads(cmc_budget_path.read_text())
    assert cg_payload["monthly_call_count"] == 140
    assert cg_payload["categories"]["markets"] == 120
    assert cg_payload["categories"]["coin_profile"] == 20
    assert cmc_payload["monthly_call_count"] == 320

    body = response.json()
    cg_usage = body["coingecko"]
    assert cg_usage["monthly_call_categories"] == {"markets": 120, "coin_profile": 20}
    reset_at = dt.datetime.fromisoformat(cg_usage["reset_at"].replace("Z", "+00:00"))
    assert reset_at.day == 1
    cmc_reset = dt.datetime.fromisoformat(body["coinmarketcap"]["reset_at"].replace("Z", "+00:00"))
    assert cmc_reset.day == 1


def test_refresh_usage_preserves_budget_on_missing_usage(monkeypatch, tmp_path):
    import backend.app.main as main_module

    monkeypatch.setattr(main_module.settings, "COINGECKO_PLAN", "demo")
    monkeypatch.setattr(main_module.settings, "COINGECKO_API_KEY", "cg-key")
    monkeypatch.setattr(main_module.settings, "coingecko_api_key", None)
    monkeypatch.setattr(main_module.settings, "CMC_API_KEY", "cmc-key")
    main_module.app.state.usage_cache = None

    cg_budget = CallBudget(tmp_path / "cg.json", quota=1000)
    cg_budget.spend(10, category="markets")
    main_module.app.state.budget = cg_budget
    main_module.app.state.cmc_budget = CallBudget(tmp_path / "cmc.json", quota=5000)

    class FakeResponse:
        def __init__(self, payload: dict[str, object]) -> None:
            self._payload = payload
            self.status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return self._payload

    def fake_get(url: str, *, headers=None, params=None, timeout=None, **kwargs):
        if "coingecko" in url:
            raise AssertionError("CoinGecko endpoint should not be called")
        if "coinmarketcap" in url:
            return FakeResponse({"data": {"usage": {"current_month": {}}}})
        raise AssertionError(f"Unexpected URL {url}")

    monkeypatch.setattr(main_module.requests, "get", fake_get)

    client = TestClient(main_module.app)
    response = client.post("/api/diag/refresh-usage")

    assert response.status_code == 200
    assert main_module.app.state.budget.monthly_call_count == 10
    assert main_module.app.state.cmc_budget.monthly_call_count == 0

