import importlib

import backend.app.core.settings as settings_module


def _setup_seed(monkeypatch):
    monkeypatch.setenv("USE_SEED_ON_FAILURE", "true")
    importlib.reload(settings_module)
    import backend.app.main as main_module

    importlib.reload(main_module)
    import backend.app.etl.run as run_module

    importlib.reload(run_module)
    monkeypatch.setattr(
        run_module, "_coingecko_etl", lambda *a, **k: (_ for _ in ()).throw(Exception())
    )
    return main_module


def test_list_cryptos_and_sorting(monkeypatch):
    main_module = _setup_seed(monkeypatch)
    resp = main_module.list_cryptos(data=main_module.get_data())
    assert resp.total == 20
    assert len(resp.items) == 20
    assert resp.items[0].latest.scores.global_ is not None

    resp = main_module.list_cryptos(
        sort="score_global", order="desc", data=main_module.get_data()
    )
    scores = [it.latest.scores.global_ for it in resp.items]
    assert scores == sorted(scores, reverse=True)


def test_get_crypto_and_history(monkeypatch):
    main_module = _setup_seed(monkeypatch)
    detail = main_module.get_crypto(1, data=main_module.get_data())
    assert detail.id == 1
    assert detail.latest.scores.liquidite is not None

    history = main_module.crypto_history(1, data=main_module.get_data())
    assert len(history.series) > 0
    assert "score_global" in history.series[0].model_dump()
