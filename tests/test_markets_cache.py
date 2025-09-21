import datetime as dt
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.db import Base
from backend.app.models import Coin, LatestPrice, Meta
from backend.app.services.dao import PricesRepo
from backend.app.services.markets_cache import MarketsCache
from backend.app.core.settings import settings


@pytest.fixture()
def setup_db(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path/'cache.db'}", connect_args={"check_same_thread": False}
    )
    TestingSessionLocal = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
    )
    Base.metadata.create_all(bind=engine)

    session = TestingSessionLocal()
    now = dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc)
    session.add(
        LatestPrice(
            coin_id="bitcoin",
            vs_currency="usd",
            price=123.0,
            market_cap=456.0,
            fully_diluted_market_cap=789.0,
            volume_24h=111.0,
            rank=1,
            pct_change_24h=1.1,
            pct_change_7d=2.2,
            pct_change_30d=3.3,
            snapshot_at=now,
        )
    )
    session.add(
        Coin(
            id="bitcoin",
            symbol="btc",
            name="Bitcoin",
            logo_url="https://img.test/bitcoin.png",
            category_names=json.dumps(["Layer 1"]),
            category_ids=json.dumps(["layer-1"]),
            social_links=json.dumps({"website": "https://bitcoin.org"}),
            updated_at=now,
        )
    )
    session.add(Meta(key="last_refresh_at", value=now.isoformat()))
    session.add(Meta(key="data_source", value="api"))
    session.commit()
    session.close()

    return TestingSessionLocal


def test_markets_cache_reuses_snapshot_within_ttl(monkeypatch, setup_db):
    TestingSessionLocal = setup_db
    monkeypatch.setattr(settings, "CG_TOP_N", 10)
    cache = MarketsCache(ttl_seconds=60)

    calls = {"count": 0}
    original_get_top = PricesRepo.get_top

    def wrapped_get_top(self, vs, limit):
        calls["count"] += 1
        return original_get_top(self, vs, limit)

    monkeypatch.setattr(PricesRepo, "get_top", wrapped_get_top)

    session1 = TestingSessionLocal()
    payload1 = cache.get_top(session1, "usd", limit=5)
    session1.close()

    assert payload1["items"]
    assert payload1["items"][0]["coin_id"] == "bitcoin"
    assert payload1["data_source"] == "api"

    session2 = TestingSessionLocal()
    payload2 = cache.get_top(session2, "usd", limit=1)
    session2.close()

    assert payload2["items"][0]["coin_id"] == "bitcoin"
    assert calls["count"] == 1
    assert payload2["items"][0]["price"] == 123.0


def test_markets_cache_refreshes_after_ttl_and_price_lookup(monkeypatch, setup_db):
    TestingSessionLocal = setup_db
    monkeypatch.setattr(settings, "CG_TOP_N", 10)
    cache = MarketsCache(ttl_seconds=60)

    current_time = {
        "now": dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc),
    }

    def fake_now():
        return current_time["now"]

    monkeypatch.setattr(cache, "_now", fake_now)

    calls = {"count": 0}
    original_get_top = PricesRepo.get_top

    def wrapped_get_top(self, vs, limit):
        calls["count"] += 1
        return original_get_top(self, vs, limit)

    monkeypatch.setattr(PricesRepo, "get_top", wrapped_get_top)

    session1 = TestingSessionLocal()
    cache.get_top(session1, "usd", limit=5)
    session1.close()
    assert calls["count"] == 1

    current_time["now"] = current_time["now"] + dt.timedelta(seconds=120)
    session2 = TestingSessionLocal()
    cache.get_top(session2, "usd", limit=5)
    assert calls["count"] == 2

    price = cache.get_price(session2, "usd", "bitcoin")
    session2.close()
    assert price is not None
    assert price["coin_id"] == "bitcoin"
    assert price["price"] == 123.0

    session3 = TestingSessionLocal()
    missing = cache.get_price(session3, "usd", "unknown")
    session3.close()
    assert missing is None
