from backend.app.services.budget import CallBudget


def test_budget_spend_and_reset(tmp_path, monkeypatch):
    path = tmp_path / "meta.json"
    budget = CallBudget(path, quota=5)
    assert budget.can_spend(5)
    budget.spend(3)
    assert not budget.can_spend(3)

    # simulate new month
    monkeypatch.setattr(budget, "_current_month", lambda: "2099-12")
    assert budget.can_spend(5)
    budget.spend(5)
    assert path.read_text() != ""
