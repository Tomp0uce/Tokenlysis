import json

from backend.app.services.budget import CallBudget


def test_budget_spend_and_reset(tmp_path, monkeypatch):
    path = tmp_path / "meta.json"
    budget = CallBudget(path, quota=5)
    assert budget.can_spend(5)
    budget.spend(3)
    assert budget.monthly_call_count == 3
    assert not budget.can_spend(3)

    # simulate new month
    monkeypatch.setattr(budget, "_current_month", lambda: "2099-12-01")
    assert budget.can_spend(5)
    budget.spend(5)
    assert budget.monthly_call_count == 5
    assert path.read_text() != ""


def test_budget_tracks_category_breakdown(tmp_path, monkeypatch):
    path = tmp_path / "budget.json"
    budget = CallBudget(path, quota=20)

    budget.spend(2, category="markets")
    budget.spend(1, category="markets")
    budget.spend(3, category="coin_profile")
    budget.spend(1)

    assert budget.monthly_call_count == 7
    assert budget.category_counts == {
        "markets": 3,
        "coin_profile": 3,
        "uncategorized": 1,
    }

    monkeypatch.setattr(budget, "_current_month", lambda: "2100-01-01")
    assert budget.can_spend(1)
    assert budget.category_counts == {}


def test_budget_sync_usage_overrides_counts(tmp_path, monkeypatch):
    path = tmp_path / "budget.json"
    budget = CallBudget(path, quota=50)

    budget.spend(5, category="markets")
    assert path.read_text()

    budget.sync_usage(monthly_call_count=42, categories={"markets": 40, "misc": 2})

    assert budget.monthly_call_count == 42
    assert budget.category_counts == {"markets": 40, "misc": 2}


def test_budget_sync_usage_ignores_invalid_data(tmp_path):
    path = tmp_path / "budget.json"
    budget = CallBudget(path, quota=50)

    budget.sync_usage(monthly_call_count=None, categories=None)
    assert budget.monthly_call_count == 0
    assert budget.category_counts == {}

    budget.sync_usage(monthly_call_count=-10, categories={"": -5, "markets": "invalid"})
    assert budget.monthly_call_count == 0
    assert budget.category_counts == {}


def test_budget_month_uses_first_day(tmp_path):
    path = tmp_path / "budget.json"
    budget = CallBudget(path, quota=50)

    budget.sync_usage(monthly_call_count=0)
    payload = json.loads(path.read_text())
    assert payload["month"].endswith("-01")

    # simulate persisted payload with old-style month
    path.write_text(json.dumps({"month": "1999-05", "monthly_call_count": 3, "categories": {}}))
    reloaded = CallBudget(path, quota=50)
    # old month triggers reset
    assert reloaded.monthly_call_count == 0
    reloaded.sync_usage(monthly_call_count=0)
    reloaded_payload = json.loads(path.read_text())
    assert reloaded_payload["month"].endswith("-01")
