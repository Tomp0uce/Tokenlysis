import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

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

    budget = CallBudget(tmp_path / "budget.json", quota=10)

    class StubClient:
        def get_markets(self, **kwargs):
            return [
                {
                    "id": "bitcoin",
                    "current_price": 1.0,
                    "market_cap": 1.0,
                    "total_volume": 1.0,
                    "market_cap_rank": 1,
                    "price_change_percentage_24h": 0.0,
                },
                {
                    "id": "ethereum",
                    "current_price": 2.0,
                    "market_cap": 2.0,
                    "total_volume": 2.0,
                    "market_cap_rank": 2,
                    "price_change_percentage_24h": 1.0,
                },
            ]

    with caplog.at_level("INFO"):
        rows = run_module.run_etl(client=StubClient(), budget=budget)
    assert rows == 2

    session = TestingSessionLocal()
    prices_repo = PricesRepo(session)
    meta_repo = MetaRepo(session)
    assert len(prices_repo.get_top("usd", 10)) == 2
    assert meta_repo.get("data_source") == "api"
    assert meta_repo.get("monthly_call_count") == "1"
    assert budget.monthly_call_count == 1
    record = next(r for r in caplog.records if r.message == "etl run completed")
    assert record.coingecko_calls_total == 1
    assert meta_repo.get("last_refresh_at") is not None
    session.close()
