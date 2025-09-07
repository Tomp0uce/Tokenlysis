import pytest

from backend.app.etl.run import run_etl, DataUnavailable
from backend.app.services.budget import CallBudget


class DummyClient:
    def get_markets(self, **kwargs):  # pragma: no cover - should not be called
        raise AssertionError("network call should be skipped")


def test_run_etl_skips_when_budget_exceeded(monkeypatch, tmp_path):
    budget = CallBudget(tmp_path / "budget.json", quota=1)
    monkeypatch.setattr(budget, "can_spend", lambda n: False)
    with pytest.raises(DataUnavailable):
        run_etl(client=DummyClient(), budget=budget)
