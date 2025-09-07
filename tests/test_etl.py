import json
import requests
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.core.settings import settings
from backend.app.db import Base
from backend.app.etl import run as run_module
from backend.app.services.budget import CallBudget
from backend.app.services.dao import PricesRepo, MetaRepo


class DummyClient:
    def get_markets(self, **kwargs):  # pragma: no cover - should not be called
        raise AssertionError("network call should be skipped")


def test_run_etl_skips_when_budget_exceeded(monkeypatch, tmp_path, caplog):
    from backend.app.etl.run import run_etl, DataUnavailable

    budget = CallBudget(tmp_path / "budget.json", quota=1)
    monkeypatch.setattr(budget, "can_spend", lambda n: False)
    with caplog.at_level("WARNING"):
        with pytest.raises(DataUnavailable):
            run_etl(client=DummyClient(), budget=budget)
    assert "quota exceeded" in caplog.text


def test_run_etl_persists_and_logs(monkeypatch, tmp_path, caplog):
    engine = create_engine(
        f"sqlite:///{tmp_path/'test.db'}", connect_args={"check_same_thread": False}
    )
    TestingSessionLocal = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
    )
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(run_module, "SessionLocal", TestingSessionLocal)

    monkeypatch.setattr(settings, "CG_TOP_N", 10)
    monkeypatch.setattr(settings, "CG_PER_PAGE_MAX", 10)

    budget = CallBudget(tmp_path / "budget.json", quota=10)

    class StubClient:
        def get_markets(self, *, vs, per_page, page):
            assert per_page == 10
            assert page == 1
            return [
                {
                    "id": f"coin{i}",
                    "current_price": float(i),
                    "market_cap": float(i),
                    "total_volume": float(i),
                    "market_cap_rank": i,
                    "price_change_percentage_24h": 0.0,
                }
                for i in range(10)
            ]

    with caplog.at_level("INFO"):
        rows = run_module.run_etl(client=StubClient(), budget=budget)
    assert rows == 10

    session = TestingSessionLocal()
    prices_repo = PricesRepo(session)
    meta_repo = MetaRepo(session)
    assert len(prices_repo.get_top("usd", 10)) == 10
    assert meta_repo.get("data_source") == "api"
    assert meta_repo.get("monthly_call_count") == "1"
    assert budget.monthly_call_count == 1
    payload = None
    for r in caplog.records:
        try:
            msg = json.loads(r.message)
        except Exception:  # pragma: no cover - non-JSON logs
            continue
        if msg.get("event") == "etl run completed":
            payload = msg
            break
    assert payload is not None
    assert payload["coingecko_calls_total"] == 1
    assert meta_repo.get("last_refresh_at") is not None
    session.close()


def test_run_etl_tracks_actual_calls(monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(settings, "CG_TOP_N", 1000)
    monkeypatch.setattr(settings, "CG_PER_PAGE_MAX", 250)

    class DummySession:
        def commit(self) -> None:  # pragma: no cover - trivial
            pass

        def rollback(self) -> None:  # pragma: no cover - trivial
            pass

        def close(self) -> None:  # pragma: no cover - trivial
            pass

    class DummyPricesRepo:
        def __init__(self, session) -> None:  # pragma: no cover - trivial
            pass

        def upsert_latest(self, rows) -> None:  # pragma: no cover - trivial
            pass

        def insert_snapshot(self, rows) -> None:  # pragma: no cover - trivial
            pass

    class DummyMetaRepo:
        last_instance = None

        def __init__(self, session) -> None:
            self.data: dict[str, str] = {}
            DummyMetaRepo.last_instance = self

        def set(self, key: str, value: str) -> None:
            self.data[key] = value

    monkeypatch.setattr(run_module, "SessionLocal", lambda: DummySession())
    monkeypatch.setattr(run_module, "PricesRepo", DummyPricesRepo)
    monkeypatch.setattr(run_module, "MetaRepo", DummyMetaRepo)

    class PagedClient:
        def __init__(self) -> None:
            self.calls: list[tuple[int, int]] = []

        def get_markets(self, *, vs: str, per_page: int, page: int):
            self.calls.append((per_page, page))
            start = (page - 1) * per_page
            return [
                {
                    "id": f"coin{start + i}",
                    "current_price": 1.0,
                    "market_cap": 1.0,
                    "total_volume": 1.0,
                    "market_cap_rank": start + i,
                    "price_change_percentage_24h": 0.0,
                }
                for i in range(per_page)
            ]

    budget = CallBudget(tmp_path / "budget.json", quota=20)
    client = PagedClient()
    with caplog.at_level("INFO"):
        rows = run_module.run_etl(client=client, budget=budget)

    assert rows == 1000
    assert budget.monthly_call_count == 4
    assert DummyMetaRepo.last_instance.data["monthly_call_count"] == "4"
    payload = None
    for r in caplog.records:
        try:
            msg = json.loads(r.message)
        except Exception:  # pragma: no cover - non-JSON logs
            continue
        if msg.get("event") == "etl run completed":
            payload = msg
            break
    assert payload is not None
    assert payload["coingecko_calls_total"] == 4
    assert [call[1] for call in client.calls] == [1, 2, 3, 4]
    assert all(call[0] == 250 for call in client.calls)


def test_run_etl_downgrades_per_page_on_4xx(monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(settings, "CG_TOP_N", 1000)
    monkeypatch.setattr(settings, "CG_PER_PAGE_MAX", 250)

    class DummySession:
        def commit(self) -> None:  # pragma: no cover - trivial
            pass

        def rollback(self) -> None:  # pragma: no cover - trivial
            pass

        def close(self) -> None:  # pragma: no cover - trivial
            pass

    class DummyPricesRepo:
        def __init__(self, session) -> None:  # pragma: no cover - trivial
            pass

        def upsert_latest(self, rows) -> None:  # pragma: no cover - trivial
            pass

        def insert_snapshot(self, rows) -> None:  # pragma: no cover - trivial
            pass

    class DummyMetaRepo:
        last_instance = None

        def __init__(self, session) -> None:
            self.data: dict[str, str] = {}
            DummyMetaRepo.last_instance = self

        def set(self, key: str, value: str) -> None:
            self.data[key] = value

    monkeypatch.setattr(run_module, "SessionLocal", lambda: DummySession())
    monkeypatch.setattr(run_module, "PricesRepo", DummyPricesRepo)
    monkeypatch.setattr(run_module, "MetaRepo", DummyMetaRepo)

    class FallbackClient:
        def __init__(self) -> None:
            self.calls: list[tuple[int, int]] = []

        def get_markets(self, *, vs: str, per_page: int, page: int):
            self.calls.append((per_page, page))
            if per_page > 100:
                response = requests.Response()
                response.status_code = 400
                raise requests.HTTPError(response=response)
            start = (page - 1) * per_page
            return [
                {
                    "id": f"coin{start + i}",
                    "current_price": 1.0,
                    "market_cap": 1.0,
                    "total_volume": 1.0,
                    "market_cap_rank": start + i,
                    "price_change_percentage_24h": 0.0,
                }
                for i in range(per_page)
            ]

    budget = CallBudget(tmp_path / "budget.json", quota=20)
    client = FallbackClient()
    with caplog.at_level("INFO"):
        rows = run_module.run_etl(client=client, budget=budget)

    assert rows == 1000
    assert budget.monthly_call_count == 10
    assert DummyMetaRepo.last_instance.data["monthly_call_count"] == "10"
    payload = None
    for r in caplog.records:
        try:
            msg = json.loads(r.message)
        except Exception:  # pragma: no cover - non-JSON logs
            continue
        if msg.get("event") == "etl run completed":
            payload = msg
            break
    assert payload is not None
    assert payload["coingecko_calls_total"] == 10
    assert client.calls[0] == (250, 1)
    assert client.calls[1:] == [(100, i) for i in range(1, 11)]
