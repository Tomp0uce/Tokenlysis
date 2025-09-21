from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.db import Base, get_session
from backend.app.services.coingecko import CoinGeckoClient
from backend.app.services.categories import slugify
from backend.app.schemas.crypto import CryptoSummary, Latest, Scores
from backend.app.schemas.price import PriceResponse
import backend.app.main as main_module
from backend.app.etl import run as run_module


class DummyResp:
    def __init__(self, data, status_code=200):
        self._data = data
        self.status_code = status_code
        self.headers = {}
        self.url = "https://example.org"

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(response=self)


def _setup_db(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path/'test.db'}", connect_args={"check_same_thread": False}
    )
    TestingSessionLocal = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
    )
    Base.metadata.create_all(bind=engine)
    return TestingSessionLocal


def test_slugify_normalizes_name():
    assert slugify("Layer 1 (L1)") == "layer-1"


def test_schema_defaults_are_independent():
    latest = Latest(
        date="2025-01-01",
        scores=Scores(global_=0, liquidite=0, opportunite=0),
    )
    a = CryptoSummary(id=1, symbol="a", name="A", sectors=[], latest=latest)
    b = CryptoSummary(id=2, symbol="b", name="B", sectors=[], latest=latest)
    a.category_names.append("foo")
    assert b.category_names == []


def test_price_response_has_category_fields():
    resp = PriceResponse(coin_id="btc", usd=1.0)
    assert resp.category_names == []
    assert resp.category_ids == []


def test_get_coin_profile(monkeypatch):
    client = CoinGeckoClient(api_key=None)

    def fake_request(self, path, params=None):
        assert path == "/coins/bitcoin"
        return DummyResp(
            {
                "categories": ["Layer 1 (L1)", "Payments"],
                "links": {
                    "homepage": ["https://bitcoin.org", ""],
                    "twitter_screen_name": "Bitcoin",
                    "subreddit_url": "https://reddit.com/r/bitcoin",
                    "repos_url": {"github": ["https://github.com/bitcoin/bitcoin"]},
                    "chat_url": [
                        "https://discord.gg/bitcoin",
                        "https://t.me/bitcoin",
                    ],
                    "telegram_channel_identifier": "bitcoin-official",
                },
            }
        )

    monkeypatch.setattr(CoinGeckoClient, "_request", fake_request)
    profile = client.get_coin_profile("bitcoin")
    assert profile["categories"] == ["Layer 1 (L1)", "Payments"]
    assert profile["links"] == {
        "website": "https://bitcoin.org",
        "twitter": "https://twitter.com/Bitcoin",
        "reddit": "https://reddit.com/r/bitcoin",
        "github": "https://github.com/bitcoin/bitcoin",
        "discord": "https://discord.gg/bitcoin",
        "telegram": "https://t.me/bitcoin",
    }


def test_etl_and_api_expose_categories(monkeypatch, tmp_path):
    TestingSessionLocal = _setup_db(tmp_path)
    monkeypatch.setattr(run_module, "SessionLocal", TestingSessionLocal)

    class StubClient:
        def get_markets(self, *, vs, per_page, page):
            return [
                {
                    "id": "bitcoin",
                    "symbol": "btc",
                    "name": "Bitcoin",
                    "current_price": 1.0,
                    "market_cap": 2.0,
                    "total_volume": 3.0,
                    "market_cap_rank": 1,
                    "price_change_percentage_24h": 4.0,
                }
            ]

        def get_categories_list(self):
            return [{"category_id": "layer-1", "name": "Layer 1 (L1)"}]

        def get_coin_categories(self, coin_id: str):
            assert coin_id == "bitcoin"
            return ["Layer 1 (L1)", "Unmapped"]

        def get_coin_profile(self, coin_id: str):
            assert coin_id == "bitcoin"
            return {
                "categories": ["Layer 1 (L1)", "Unmapped"],
                "links": {
                    "website": "https://bitcoin.org",
                    "twitter": "https://twitter.com/bitcoin",
                    "reddit": "https://reddit.com/r/bitcoin",
                    "github": "https://github.com/bitcoin/bitcoin",
                    "discord": "https://discord.gg/bitcoin",
                    "telegram": "https://t.me/bitcoin",
                },
            }

    run_module.run_etl(client=StubClient(), budget=None)

    main_module.app.dependency_overrides[get_session] = lambda: TestingSessionLocal()
    client = TestClient(main_module.app)
    resp = client.get("/api/coins/bitcoin/categories")
    assert resp.status_code == 200
    data = resp.json()
    assert data["category_names"] == ["Layer 1 (L1)", "Unmapped"]
    assert data["category_ids"] == ["layer-1", "unmapped"]
    resp2 = client.get("/api/markets/top?limit=1&vs=usd")
    assert resp2.status_code == 200
    item = resp2.json()["items"][0]
    assert item["category_ids"] == ["layer-1", "unmapped"]
    assert item["social_links"]["website"] == "https://bitcoin.org"
    resp3 = client.get("/api/price/bitcoin")
    assert resp3.status_code == 200
    data3 = resp3.json()
    assert data3["category_ids"] == ["layer-1", "unmapped"]
    assert data3["social_links"]["twitter"] == "https://twitter.com/bitcoin"


def test_etl_skips_category_fetch_if_recent(monkeypatch, tmp_path):
    TestingSessionLocal = _setup_db(tmp_path)
    monkeypatch.setattr(run_module, "SessionLocal", TestingSessionLocal)

    class StubClient:
        def __init__(self) -> None:
            self.cat_calls = 0

        def get_markets(self, *, vs, per_page, page):
            return [
                {
                    "id": "bitcoin",
                    "symbol": "btc",
                    "name": "Bitcoin",
                    "current_price": 1.0,
                    "market_cap": 2.0,
                    "total_volume": 3.0,
                    "market_cap_rank": 1,
                    "price_change_percentage_24h": 4.0,
                }
            ]

        def get_categories_list(self):
            return []

        def get_coin_categories(self, coin_id: str):
            self.cat_calls += 1
            return []

        def get_coin_profile(self, coin_id: str):
            self.cat_calls += 1
            return {"categories": [], "links": {}}

    client = StubClient()
    run_module.run_etl(client=client, budget=None)
    assert client.cat_calls == 1
    run_module.run_etl(client=client, budget=None)
    assert client.cat_calls == 1
