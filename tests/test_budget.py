from backend.app.services.budget import CallBudget


def test_budget_spend_and_reset(tmp_path, monkeypatch):
    path = tmp_path / "meta.json"
    budget = CallBudget(path, quota=5)
    assert budget.can_spend(5)
    budget.spend(3)
    assert budget.monthly_call_count == 3
    assert not budget.can_spend(3)

    # simulate new month
    monkeypatch.setattr(budget, "_current_month", lambda: "2099-12")
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

    monkeypatch.setattr(budget, "_current_month", lambda: "2100-01")
    assert budget.can_spend(1)
    assert budget.category_counts == {}
