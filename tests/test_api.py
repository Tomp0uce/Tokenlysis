from backend.app.main import crypto_history, get_crypto, list_cryptos, get_data


def test_list_cryptos_and_sorting():
    resp = list_cryptos(data=get_data())
    assert resp.total == 20
    assert len(resp.items) == 20
    assert resp.items[0].latest.scores.global_ is not None

    resp = list_cryptos(sort="score_global", order="desc", data=get_data())
    scores = [it.latest.scores.global_ for it in resp.items]
    assert scores == sorted(scores, reverse=True)


def test_get_crypto_and_history():
    detail = get_crypto(1, data=get_data())
    assert detail.id == 1
    assert detail.latest.scores.liquidite is not None

    history = crypto_history(1, data=get_data())
    assert len(history.series) > 0
    assert "score_global" in history.series[0].model_dump()
