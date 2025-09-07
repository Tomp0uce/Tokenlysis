from backend.app.services.budget import CallBudget
from backend.app.etl import run as etl_run


class DummyClient:
    api_key = None


def test_run_etl_uses_full_top_n_without_api_key(monkeypatch, tmp_path):
    monkeypatch.setattr(etl_run.settings, "CG_TOP_N", 300)
    monkeypatch.setattr(etl_run.settings, "CG_PER_PAGE_MAX", 250)

    captured = {}

    def fake_etl(limit, days, client, per_page_max):
        captured["limit"] = limit
        return {}

    monkeypatch.setattr(etl_run, "_coingecko_etl", fake_etl)
    budget = CallBudget(tmp_path / "budget.json", quota=10)
    etl_run.run_etl(client=DummyClient(), budget=budget)

    assert captured["limit"] == 300
    assert budget.monthly_call_count == 2
