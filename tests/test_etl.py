import asyncio
import contextlib
import datetime as dt
import json
import requests
import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from backend.app.core.settings import settings
from backend.app.db import Base
from backend.app.etl import run as run_module
from backend.app.models import Coin
from backend.app.services.budget import CallBudget
from backend.app.services.dao import PricesRepo, MetaRepo
import backend.app.main as main_module


class DummyClient:
    def get_markets(self, **kwargs):  # pragma: no cover - should not be called
        raise AssertionError("network call should be skipped")


def test_run_etl_skips_when_budget_exceeded(monkeypatch, tmp_path, caplog):
    from backend.app.etl.run import run_etl, DataUnavailable

    budget = CallBudget(tmp_path / "budget.json", quota=1)
    monkeypatch.setattr(budget, "can_spend", lambda n: False)
    with caplog.at_level("WARNING"):
        with pytest.raises(DataUnavailable):
            run_etl(client=DummyClient(), budget=budget)
    assert "quota exceeded" in caplog.text


def test_run_etl_persists_and_logs(monkeypatch, tmp_path, caplog):
    engine = create_engine(
        f"sqlite:///{tmp_path/'test.db'}", connect_args={"check_same_thread": False}
    )
    TestingSessionLocal = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
    )
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(run_module, "SessionLocal", TestingSessionLocal)

    monkeypatch.setattr(settings, "CG_TOP_N", 10)
    monkeypatch.setattr(settings, "CG_PER_PAGE_MAX", 10)
    monkeypatch.setattr(run_module, "_categories_cache", {})
    monkeypatch.setattr(run_module, "_categories_cache_ts", None)

    budget = CallBudget(tmp_path / "budget.json", quota=20)

    class StubClient:
        def get_markets(self, *, vs, per_page, page):
            assert per_page == 10
            assert page == 1
            return [
                {
                    "id": f"coin{i}",
                    "name": f"Coin {i}",
                    "symbol": f"c{i}",
                    "image": f"https://img.test/coin{i}.png",
                    "current_price": float(i),
                    "market_cap": float(i),
                    "total_volume": float(i),
                    "market_cap_rank": i,
                    "price_change_percentage_24h": 0.0,
                }
                for i in range(10)
            ]

        def get_categories_list(self):
            return []

        def get_coin_profile(self, coin_id: str):
            return {
                "categories": [],
                "links": {
                    "website": f"https://{coin_id}.org",
                    "twitter": f"https://twitter.com/{coin_id}",
                },
            }

    with caplog.at_level("INFO"):
        rows = run_module.run_etl(client=StubClient(), budget=budget)
    assert rows == 10

    session = TestingSessionLocal()
    prices_repo = PricesRepo(session)
    meta_repo = MetaRepo(session)
    assert len(prices_repo.get_top("usd", 10)) == 10
    assert meta_repo.get("data_source") == "api"
    assert meta_repo.get("monthly_call_count") == "12"
    assert meta_repo.get("last_etl_items") == "10"
    assert budget.monthly_call_count == 12
    payload = None
    for r in caplog.records:
        try:
            msg = json.loads(r.message)
        except Exception:  # pragma: no cover - non-JSON logs
            continue
        if msg.get("event") == "etl run completed":
            payload = msg
            break
    assert payload is not None
    assert payload["coingecko_calls_total"] == 12
    assert meta_repo.get("last_refresh_at") is not None
    coins = session.query(Coin).order_by(Coin.id).all()
    assert coins
    assert coins[0].name == "Coin 0"
    assert coins[0].logo_url == "https://img.test/coin0.png"
    assert json.loads(coins[0].social_links or "{}")["website"] == "https://coin0.org"
    session.close()


def test_run_etl_tracks_actual_calls(monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(settings, "CG_TOP_N", 1000)
    monkeypatch.setattr(settings, "CG_PER_PAGE_MAX", 250)

    class DummySession:
        def commit(self) -> None:  # pragma: no cover - trivial
            pass

        def rollback(self) -> None:  # pragma: no cover - trivial
            pass

        def close(self) -> None:  # pragma: no cover - trivial
            pass

    class DummyPricesRepo:
        def __init__(self, session) -> None:  # pragma: no cover - trivial
            pass

        def upsert_latest(self, rows) -> None:  # pragma: no cover - trivial
            pass

        def insert_snapshot(self, rows) -> None:  # pragma: no cover - trivial
            pass

    class DummyMetaRepo:
        last_instance = None

        def __init__(self, session) -> None:
            self.data: dict[str, str] = {}
            DummyMetaRepo.last_instance = self

        def set(self, key: str, value: str) -> None:
            self.data[key] = value

    class DummyCoinsRepo:
        def __init__(self, session) -> None:  # pragma: no cover - trivial
            pass

        def upsert(self, rows) -> None:  # pragma: no cover - trivial
            pass

        def get_categories_with_timestamp(self, coin_id):  # pragma: no cover - trivial
            return [], [], {"__synced__": True}, dt.datetime.now(dt.timezone.utc)

    monkeypatch.setattr(run_module, "SessionLocal", lambda: DummySession())
    monkeypatch.setattr(run_module, "PricesRepo", DummyPricesRepo)
    monkeypatch.setattr(run_module, "MetaRepo", DummyMetaRepo)
    monkeypatch.setattr(run_module, "CoinsRepo", DummyCoinsRepo)
    monkeypatch.setattr(
        run_module,
        "_categories_cache_ts",
        dt.datetime.now(dt.timezone.utc),
    )
    monkeypatch.setattr(run_module, "_categories_cache", {})

    class PagedClient:
        def __init__(self) -> None:
            self.calls: list[tuple[int, int]] = []

        def get_markets(self, *, vs: str, per_page: int, page: int):
            self.calls.append((per_page, page))
            start = (page - 1) * per_page
            return [
                {
                    "id": f"coin{start + i}",
                    "current_price": 1.0,
                    "market_cap": 1.0,
                    "total_volume": 1.0,
                    "market_cap_rank": start + i,
                    "price_change_percentage_24h": 0.0,
                }
                for i in range(per_page)
            ]

        def get_categories_list(self):  # pragma: no cover - trivial
            return []

        def get_coin_profile(self, coin_id: str):  # pragma: no cover - trivial
            return {"categories": [], "links": {}}

    budget = CallBudget(tmp_path / "budget.json", quota=20)
    client = PagedClient()
    with caplog.at_level("INFO"):
        rows = run_module.run_etl(client=client, budget=budget)

    assert rows == 1000
    assert budget.monthly_call_count == 4
    assert DummyMetaRepo.last_instance.data["monthly_call_count"] == "4"
    payload = None
    for r in caplog.records:
        try:
            msg = json.loads(r.message)
        except Exception:  # pragma: no cover - non-JSON logs
            continue
        if msg.get("event") == "etl run completed":
            payload = msg
            break
    assert payload is not None
    assert payload["coingecko_calls_total"] == 4
    assert [call[1] for call in client.calls] == [1, 2, 3, 4]
    assert all(call[0] == 250 for call in client.calls)


def test_run_etl_downgrades_per_page_on_4xx(monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(settings, "CG_TOP_N", 1000)
    monkeypatch.setattr(settings, "CG_PER_PAGE_MAX", 250)

    class DummySession:
        def commit(self) -> None:  # pragma: no cover - trivial
            pass

        def rollback(self) -> None:  # pragma: no cover - trivial
            pass

        def close(self) -> None:  # pragma: no cover - trivial
            pass

    class DummyPricesRepo:
        def __init__(self, session) -> None:  # pragma: no cover - trivial
            pass

        def upsert_latest(self, rows) -> None:  # pragma: no cover - trivial
            pass

        def insert_snapshot(self, rows) -> None:  # pragma: no cover - trivial
            pass

    class DummyMetaRepo:
        last_instance = None

        def __init__(self, session) -> None:
            self.data: dict[str, str] = {}
            DummyMetaRepo.last_instance = self

        def set(self, key: str, value: str) -> None:
            self.data[key] = value

    class DummyCoinsRepo:
        def __init__(self, session) -> None:  # pragma: no cover - trivial
            pass

        def upsert(self, rows) -> None:  # pragma: no cover - trivial
            pass

        def get_categories_with_timestamp(self, coin_id):  # pragma: no cover - trivial
            return [], [], {}, dt.datetime.now(dt.timezone.utc)

    monkeypatch.setattr(run_module, "SessionLocal", lambda: DummySession())
    monkeypatch.setattr(run_module, "PricesRepo", DummyPricesRepo)
    monkeypatch.setattr(run_module, "MetaRepo", DummyMetaRepo)
    monkeypatch.setattr(run_module, "CoinsRepo", DummyCoinsRepo)

    class FallbackClient:
        def __init__(self) -> None:
            self.calls: list[tuple[int, int]] = []

        def get_markets(self, *, vs: str, per_page: int, page: int):
            self.calls.append((per_page, page))
            if per_page > 100:
                response = requests.Response()
                response.status_code = 400
                raise requests.HTTPError(response=response)
            start = (page - 1) * per_page
            return [
                {
                    "id": f"coin{start + i}",
                    "current_price": 1.0,
                    "market_cap": 1.0,
                    "total_volume": 1.0,
                    "market_cap_rank": start + i,
                    "price_change_percentage_24h": 0.0,
                }
                for i in range(per_page)
            ]

    budget = CallBudget(tmp_path / "budget.json", quota=20)
    client = FallbackClient()
    with caplog.at_level("INFO"):
        rows = run_module.run_etl(client=client, budget=budget)

    assert rows == 1000
    assert budget.monthly_call_count == 11
    assert DummyMetaRepo.last_instance.data["monthly_call_count"] == "11"
    payload = None
    for r in caplog.records:
        try:
            msg = json.loads(r.message)
        except Exception:  # pragma: no cover - non-JSON logs
            continue
        if msg.get("event") == "etl run completed":
            payload = msg
            break
    assert payload is not None
    assert payload["coingecko_calls_total"] == 11
    assert len(client.calls) == 11
    assert client.calls[0] == (250, 1)
    assert client.calls[1:] == [(100, i) for i in range(1, 11)]


def test_run_etl_stops_when_budget_exhausted(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "CG_TOP_N", 1000)
    monkeypatch.setattr(settings, "CG_PER_PAGE_MAX", 250)

    class DummySession:
        def commit(self) -> None:  # pragma: no cover - trivial
            pass

        def rollback(self) -> None:  # pragma: no cover - trivial
            pass

        def close(self) -> None:  # pragma: no cover - trivial
            pass

    class DummyPricesRepo:
        def __init__(self, session) -> None:  # pragma: no cover - trivial
            pass

        def upsert_latest(self, rows) -> None:  # pragma: no cover - trivial
            pass

        def insert_snapshot(self, rows) -> None:  # pragma: no cover - trivial
            pass

    class DummyMetaRepo:
        last_instance = None

        def __init__(self, session) -> None:
            self.data: dict[str, str] = {}
            DummyMetaRepo.last_instance = self

        def set(self, key: str, value: str) -> None:
            self.data[key] = value

    class DummyCoinsRepo:
        def __init__(self, session) -> None:  # pragma: no cover - trivial
            pass

        def upsert(self, rows) -> None:  # pragma: no cover - trivial
            pass

        def get_categories_with_timestamp(self, coin_id):  # pragma: no cover - trivial
            return [], [], {}, dt.datetime.now(dt.timezone.utc)

    monkeypatch.setattr(run_module, "SessionLocal", lambda: DummySession())
    monkeypatch.setattr(run_module, "PricesRepo", DummyPricesRepo)
    monkeypatch.setattr(run_module, "MetaRepo", DummyMetaRepo)
    monkeypatch.setattr(run_module, "CoinsRepo", DummyCoinsRepo)

    class PagedClient:
        def __init__(self) -> None:
            self.calls: list[tuple[int, int]] = []

        def get_markets(self, *, vs: str, per_page: int, page: int):
            self.calls.append((per_page, page))
            start = (page - 1) * per_page
            return [
                {
                    "id": f"coin{start + i}",
                    "current_price": 1.0,
                    "market_cap": 1.0,
                    "total_volume": 1.0,
                    "market_cap_rank": start + i,
                    "price_change_percentage_24h": 0.0,
                }
                for i in range(per_page)
            ]

    budget = CallBudget(tmp_path / "budget.json", quota=3)
    client = PagedClient()
    with pytest.raises(run_module.DataUnavailable):
        run_module.run_etl(client=client, budget=budget)

    assert budget.monthly_call_count == 3
    assert len(client.calls) == 3
    assert DummyMetaRepo.last_instance is None


def test_run_etl_backfills_missing_categories(monkeypatch, tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path/'test.db'}", connect_args={"check_same_thread": False}
    )
    TestingSessionLocal = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
    )
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    session.add(
        Coin(
            id="bitcoin",
            symbol="btc",
            name="Bitcoin",
            category_names=None,
            category_ids=None,
            updated_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=2),
        )
    )
    session.commit()
    session.close()
    monkeypatch.setattr(run_module, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(run_module, "_categories_cache", {})
    monkeypatch.setattr(run_module, "_categories_cache_ts", None)

    class StubClient:
        def __init__(self) -> None:
            self.cat_calls = 0
            self.list_calls = 0

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
            self.list_calls += 1
            return [{"category_id": "layer-1", "name": "Layer 1"}]

        def get_coin_categories(self, coin_id):
            self.cat_calls += 1
            return ["Layer 1"]

        def get_coin_profile(self, coin_id):
            self.cat_calls += 1
            return {"categories": ["Layer 1"], "links": {}}

    client = StubClient()
    run_module.run_etl(client=client, budget=None)
    assert client.cat_calls == 1
    assert client.list_calls == 1
    session = TestingSessionLocal()
    names, ids, links, _ = run_module.CoinsRepo(session).get_categories_with_timestamp(
        "bitcoin"
    )
    session.close()
    assert names == ["Layer 1"]
    assert ids == ["layer-1"]
    assert links == {"__synced__": True}

    run_module.run_etl(client=client, budget=None)
    assert client.cat_calls == 1
    assert client.list_calls == 1


def test_run_etl_backfills_missing_links(monkeypatch, tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path/'test.db'}", connect_args={"check_same_thread": False}
    )
    TestingSessionLocal = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
    )
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    session.add(
        Coin(
            id="bitcoin",
            symbol="btc",
            name="Bitcoin",
            category_names=json.dumps(["Layer 1"]),
            category_ids=json.dumps(["layer-1"]),
            social_links=json.dumps({}),
            updated_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1),
        )
    )
    session.commit()
    session.close()

    monkeypatch.setattr(run_module, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(run_module, "_categories_cache", {})
    monkeypatch.setattr(run_module, "_categories_cache_ts", None)

    class StubClient:
        def __init__(self) -> None:
            self.profile_calls = 0

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

        def get_coin_profile(self, coin_id: str):
            self.profile_calls += 1
            return {
                "categories": ["Layer 1"],
                "links": {"website": "https://bitcoin.org"},
            }

    client = StubClient()
    run_module.run_etl(client=client, budget=None)
    assert client.profile_calls == 1

    session = TestingSessionLocal()
    names, ids, links, _ = run_module.CoinsRepo(session).get_categories_with_timestamp(
        "bitcoin"
    )
    session.close()
    assert names == ["Layer 1"]
    assert ids == ["layer-1"]
    assert links.get("website") == "https://bitcoin.org"
    assert "__synced__" not in links

    run_module.run_etl(client=client, budget=None)
    assert client.profile_calls == 1


def test_run_etl_preserves_categories_when_profile_fetch_fails(
    monkeypatch, tmp_path
):
    engine = create_engine(
        f"sqlite:///{tmp_path/'test.db'}", connect_args={"check_same_thread": False}
    )
    TestingSessionLocal = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
    )
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    session.add(
        Coin(
            id="bitcoin",
            symbol="btc",
            name="Bitcoin",
            category_names=json.dumps(["Layer 1"]),
            category_ids=json.dumps(["layer-1"]),
            social_links=json.dumps({}),
            updated_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1),
        )
    )
    session.commit()
    session.close()

    monkeypatch.setattr(run_module, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(run_module, "_categories_cache", {})
    monkeypatch.setattr(run_module, "_categories_cache_ts", None)

    class StubClient:
        def __init__(self) -> None:
            self.profile_calls = 0

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

        def get_coin_profile(self, coin_id: str):
            self.profile_calls += 1
            raise requests.HTTPError("boom")

    client = StubClient()
    run_module.run_etl(client=client, budget=None)
    assert client.profile_calls == 1

    session = TestingSessionLocal()
    names, ids, links, _ = run_module.CoinsRepo(session).get_categories_with_timestamp(
        "bitcoin"
    )
    session.close()
    assert names == ["Layer 1"]
    assert ids == ["layer-1"]
    assert links == {}


def test_run_etl_retries_on_429(monkeypatch, tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path/'test.db'}", connect_args={"check_same_thread": False}
    )
    TestingSessionLocal = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
    )
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    session.add(
        Coin(
            id="bitcoin",
            symbol="btc",
            name="Bitcoin",
            category_names=None,
            category_ids=None,
            updated_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=2),
        )
    )
    session.commit()
    session.close()
    monkeypatch.setattr(run_module, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(run_module, "_categories_cache", {})
    monkeypatch.setattr(run_module, "_categories_cache_ts", None)

    class StubClient:
        def __init__(self) -> None:
            self.cat_calls = 0
            self.resp = requests.Response()
            self.resp.status_code = 429

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

        def get_coin_categories(self, coin_id):
            self.cat_calls += 1
            raise requests.HTTPError(response=self.resp)

        def get_coin_profile(self, coin_id):
            self.cat_calls += 1
            raise requests.HTTPError(response=self.resp)

    sleep_calls: list[float] = []
    monkeypatch.setattr(run_module.time, "sleep", lambda s: sleep_calls.append(s))

    client = StubClient()
    run_module.run_etl(client=client, budget=None)
    assert client.cat_calls == 4
    assert sleep_calls[:3] == [0.25, 1.0, 2.0]
    session = TestingSessionLocal()
    names, ids, links, _ = run_module.CoinsRepo(session).get_categories_with_timestamp(
        "bitcoin"
    )
    session.close()
    assert names == [] and ids == []
    assert links == {}


def test_etl_loop_handles_operational_error(monkeypatch):
    async def boom_async(*, budget):
        raise OperationalError("stmt", {}, "err")

    async def fake_wait_for(awaitable, timeout):
        task = asyncio.create_task(awaitable)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        raise asyncio.CancelledError

    monkeypatch.setattr(main_module, "run_etl_async", boom_async)
    monkeypatch.setattr(main_module, "refresh_interval_seconds", lambda value=None: 0)
    monkeypatch.setattr(main_module.asyncio, "wait_for", fake_wait_for)
    monkeypatch.setattr(main_module.app.state, "budget", None, raising=False)
    stop_event = asyncio.Event()
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(main_module.etl_loop(stop_event))
