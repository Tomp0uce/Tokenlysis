from backend.app.etl.run import _coin_history


class DummyClient:
    def __init__(self) -> None:
        self.called_with = None

    def get_market_chart(self, coin_id: str, days: int):
        self.called_with = (coin_id, days)
        return {"prices": []}


def test_coin_history_uses_coingecko_id():
    coin = {"coingecko_id": "bitcoin", "symbol": "btc", "id": "btc"}
    client = DummyClient()
    _coin_history(coin, 14, client)
    assert client.called_with == ("bitcoin", 14)


def test_coin_history_maps_seed_symbol():
    coin = {"symbol": "C1", "id": "1"}
    client = DummyClient()
    _coin_history(coin, 14, client)
    assert client.called_with == ("bitcoin", 14)
