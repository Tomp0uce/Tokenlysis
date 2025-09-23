import datetime as dt

import pytest
import requests
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.services.budget import CallBudget


@pytest.fixture()
def TestingSessionLocal(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path/'fear_greed.db'}", connect_args={"check_same_thread": False}
    )
    TestingSessionLocal = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
    )
    from backend.app.db import Base
    import backend.app.models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    return TestingSessionLocal


def test_fear_greed_repo_upsert_and_history(TestingSessionLocal):
    from backend.app.services.dao import FearGreedRepo
    from backend.app.models import FearGreed

    session = TestingSessionLocal()
    repo = FearGreedRepo(session)

    ts1 = dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc)
    ts2 = dt.datetime(2024, 1, 2, tzinfo=dt.timezone.utc)
    ts3 = dt.datetime(2024, 1, 3, tzinfo=dt.timezone.utc)

    repo.upsert_many(
        [
            {
                "timestamp": ts2,
                "value": 40,
                "classification": "Fear",
                "ingested_at": ts3,
            },
            {
                "timestamp": ts1,
                "value": 25,
                "classification": "Extreme Fear",
                "ingested_at": ts3,
            },
            {
                "timestamp": ts2,
                "value": 45,
                "classification": "Fear",
                "ingested_at": ts3,
            },
        ]
    )
    session.commit()

    latest = repo.get_latest()
    assert isinstance(latest, FearGreed)
    assert latest.timestamp == ts2
    assert latest.value == 45

    history = repo.get_history(since=ts2)
    assert [row.timestamp for row in history] == [ts2]

    full_history = repo.get_history()
    assert [row.timestamp for row in full_history] == [ts1, ts2]
    assert repo.count() == 2
    session.close()


def test_api_fng_latest_success(monkeypatch, TestingSessionLocal):
    import backend.app.main as main_module

    class StubClient:
        def __init__(self) -> None:
            self.latest_calls = 0
            self.history_calls: list[dict[str, object]] = []

        def get_latest(self) -> dict:
            self.latest_calls += 1
            return {
                "timestamp": "2024-03-10T00:00:00+00:00",
                "score": 58,
                "label": "Greed",
            }

        def get_historical(
            self, *, limit: int | None = None, time_start: str | None = None, time_end: str | None = None
        ) -> list[dict]:
            self.history_calls.append({
                "limit": limit,
                "time_start": time_start,
                "time_end": time_end,
            })
            return []

    stub = StubClient()

    session = TestingSessionLocal()

    def override_session():
        try:
            yield session
        finally:
            pass

    main_module.app.dependency_overrides[main_module.get_session] = override_session
    main_module.app.dependency_overrides[main_module.get_fng_client] = lambda: stub
    main_module.app.state.cmc_budget = None

    client = TestClient(main_module.app)
    resp = client.get("/api/fng/latest")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload == {
        "timestamp": "2024-03-10T00:00:00+00:00",
        "score": 58,
        "label": "Greed",
    }
    assert stub.latest_calls == 1
    assert stub.history_calls == [
        {"limit": None, "time_start": None, "time_end": None}
    ]

    main_module.app.dependency_overrides.pop(main_module.get_session, None)
    main_module.app.dependency_overrides.pop(main_module.get_fng_client, None)
    session.close()


def test_api_fng_latest_falls_back_to_history(monkeypatch, TestingSessionLocal):
    import backend.app.main as main_module

    class StubClient:
        def __init__(self) -> None:
            self.history_calls: list[dict[str, object]] = []

        def get_latest(self) -> dict:
            raise requests.RequestException("boom")

        def get_historical(
            self, *, limit: int | None = None, time_start: str | None = None, time_end: str | None = None
        ) -> list[dict]:
            self.history_calls.append({
                "limit": limit,
                "time_start": time_start,
                "time_end": time_end,
            })
            return [
                {
                    "timestamp": "2024-03-09T00:00:00+00:00",
                    "score": 20,
                    "label": "Fear",
                },
                {
                    "timestamp": "2024-03-11T00:00:00+00:00",
                    "score": 35,
                    "label": "Neutral",
                },
            ]

    stub = StubClient()

    session = TestingSessionLocal()

    def override_session():
        try:
            yield session
        finally:
            pass

    main_module.app.dependency_overrides[main_module.get_session] = override_session
    main_module.app.dependency_overrides[main_module.get_fng_client] = lambda: stub
    main_module.app.state.cmc_budget = None

    client = TestClient(main_module.app)
    resp = client.get("/api/fng/latest")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["score"] == 35
    assert payload["label"] == "Neutral"
    assert payload["timestamp"].startswith("2024-03-11")
    assert stub.history_calls == [
        {"limit": None, "time_start": None, "time_end": None}
    ]

    main_module.app.dependency_overrides.pop(main_module.get_session, None)
    main_module.app.dependency_overrides.pop(main_module.get_fng_client, None)
    session.close()


def test_api_fng_latest_uses_database_fallback(monkeypatch, TestingSessionLocal):
    import backend.app.main as main_module

    class StubClient:
        def get_latest(self) -> dict:
            raise requests.RequestException("down")

        def get_historical(self, **_: object) -> list[dict]:
            raise requests.RequestException("down history")

    session = TestingSessionLocal()
    from backend.app.services.dao import FearGreedRepo

    repo = FearGreedRepo(session)
    ts = dt.datetime(2024, 4, 1, tzinfo=dt.timezone.utc)
    repo.upsert_many(
        [
            {
                "timestamp": ts,
                "value": 42,
                "classification": "Greed",
                "ingested_at": ts,
            }
        ]
    )
    session.commit()

    def override_session():
        try:
            yield session
        finally:
            pass

    main_module.app.dependency_overrides[main_module.get_session] = override_session
    main_module.app.dependency_overrides[main_module.get_fng_client] = lambda: StubClient()
    main_module.app.state.cmc_budget = None

    client = TestClient(main_module.app)
    resp = client.get("/api/fng/latest")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["score"] == 42
    assert payload["label"] == "Greed"
    assert payload["timestamp"].startswith("2024-04-01")

    main_module.app.dependency_overrides.pop(main_module.get_session, None)
    main_module.app.dependency_overrides.pop(main_module.get_fng_client, None)
    session.close()


def test_api_fng_latest_uses_cache_when_refresh_recent(
    monkeypatch, TestingSessionLocal
):
    import backend.app.main as main_module
    from backend.app.core.settings import settings
    from backend.app.services.dao import FearGreedRepo, MetaRepo

    monkeypatch.setattr(settings, "REFRESH_GRANULARITY", "48h")

    session = TestingSessionLocal()
    repo = FearGreedRepo(session)
    meta_repo = MetaRepo(session)

    timestamp = dt.datetime(2024, 5, 5, 12, 0, tzinfo=dt.timezone.utc)
    repo.upsert_many(
        [
            {
                "timestamp": timestamp,
                "value": 62,
                "classification": "Greed",
                "ingested_at": timestamp,
            }
        ]
    )
    meta_repo.set(
        "fear_greed_last_refresh",
        (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=30)).isoformat(),
    )
    session.commit()

    def override_session():
        try:
            yield session
        finally:
            pass

    class StubClient:
        def get_latest(self, *args, **kwargs):  # pragma: no cover - should not run
            raise AssertionError("latest fetch should not execute when fresh")

        def get_historical(self, *args, **kwargs):  # pragma: no cover - should not run
            raise AssertionError("history fetch should not execute when fresh")

    main_module.app.dependency_overrides[main_module.get_session] = override_session
    main_module.app.dependency_overrides[main_module.get_fng_client] = lambda: StubClient()

    client = TestClient(main_module.app)
    resp = client.get("/api/fng/latest")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["score"] == 62
    assert payload["label"] == "Greed"
    assert payload["timestamp"].startswith("2024-05-05T12:00:00")

    main_module.app.dependency_overrides.pop(main_module.get_session, None)
    main_module.app.dependency_overrides.pop(main_module.get_fng_client, None)
    session.close()


def test_api_fng_latest_propagates_errors(monkeypatch, TestingSessionLocal):
    import backend.app.main as main_module

    class StubClient:
        def get_latest(self) -> dict:
            raise requests.RequestException("fail latest")

        def get_historical(self, **_: object) -> list[dict]:
            raise requests.RequestException("fail history")

    stub = StubClient()

    session = TestingSessionLocal()

    def override_session():
        try:
            yield session
        finally:
            pass

    main_module.app.dependency_overrides[main_module.get_session] = override_session
    main_module.app.dependency_overrides[main_module.get_fng_client] = lambda: stub
    main_module.app.state.cmc_budget = None

    client = TestClient(main_module.app)
    resp = client.get("/api/fng/latest")
    assert resp.status_code == 502
    payload = resp.json()
    assert "fear & greed" in payload.get("detail", "").lower()

    main_module.app.dependency_overrides.pop(main_module.get_session, None)
    main_module.app.dependency_overrides.pop(main_module.get_fng_client, None)
    session.close()


def test_api_fng_history_orders_points(monkeypatch, TestingSessionLocal):
    import backend.app.main as main_module

    class StubClient:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def get_latest(self) -> dict | None:
            return None

        def get_historical(
            self, *, limit: int | None = None, time_start: str | None = None, time_end: str | None = None
        ) -> list[dict]:
            self.calls.append({
                "limit": limit,
                "time_start": time_start,
                "time_end": time_end,
            })
            return [
                {
                    "timestamp": "2024-03-15T00:00:00+00:00",
                    "score": 55,
                    "label": "Greed",
                },
                {
                    "timestamp": "2024-03-12T00:00:00+00:00",
                    "score": 25,
                    "label": "Fear",
                },
            ]

    stub = StubClient()
    session = TestingSessionLocal()

    def override_session():
        try:
            yield session
        finally:
            pass

    main_module.app.dependency_overrides[main_module.get_session] = override_session
    main_module.app.dependency_overrides[main_module.get_fng_client] = lambda: stub
    main_module.app.state.cmc_budget = None

    client = TestClient(main_module.app)
    resp = client.get("/api/fng/history?days=5")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["days"] == 5
    assert [point["score"] for point in payload["points"]] == [25, 55]
    assert stub.calls == [
        {"limit": None, "time_start": None, "time_end": None}
    ]

    main_module.app.dependency_overrides.pop(main_module.get_fng_client, None)
    main_module.app.dependency_overrides.pop(main_module.get_session, None)
    session.close()


def test_api_fng_history_uses_database_fallback(monkeypatch, TestingSessionLocal):
    import backend.app.main as main_module

    class StubClient:
        def get_historical(self, **_: object) -> list[dict]:
            raise requests.RequestException("history offline")

        def get_latest(self) -> dict | None:
            return None

    session = TestingSessionLocal()
    from backend.app.services.dao import FearGreedRepo

    repo = FearGreedRepo(session)
    ts1 = dt.datetime(2024, 3, 1, tzinfo=dt.timezone.utc)
    ts2 = dt.datetime(2024, 3, 2, tzinfo=dt.timezone.utc)
    ts3 = dt.datetime(2024, 3, 3, tzinfo=dt.timezone.utc)
    repo.upsert_many(
        [
            {
                "timestamp": ts1,
                "value": 10,
                "classification": "Extreme Fear",
                "ingested_at": ts3,
            },
            {
                "timestamp": ts2,
                "value": 55,
                "classification": "Neutral",
                "ingested_at": ts3,
            },
            {
                "timestamp": ts3,
                "value": 75,
                "classification": "Greed",
                "ingested_at": ts3,
            },
        ]
    )
    session.commit()

    def override_session():
        try:
            yield session
        finally:
            pass

    main_module.app.dependency_overrides[main_module.get_session] = override_session
    main_module.app.dependency_overrides[main_module.get_fng_client] = lambda: StubClient()

    client = TestClient(main_module.app)
    resp = client.get("/api/fng/history?days=2")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["days"] == 2
    assert [point["score"] for point in payload["points"]] == [55, 75]
    assert payload["points"][0]["timestamp"].startswith("2024-03-02")
    assert payload["points"][1]["label"] == "Greed"

    main_module.app.dependency_overrides.pop(main_module.get_session, None)
    main_module.app.dependency_overrides.pop(main_module.get_fng_client, None)
    session.close()


def test_api_fng_history_rejects_invalid_days(monkeypatch):
    import backend.app.main as main_module

    class StubClient:
        def get_latest(self) -> dict:
            raise AssertionError("should not fetch latest")

        def get_historical(self, **_: object) -> list[dict]:
            raise AssertionError("should not fetch history")

    main_module.app.dependency_overrides[main_module.get_fng_client] = lambda: StubClient()

    client = TestClient(main_module.app)
    resp = client.get("/api/fng/history?days=0")
    assert resp.status_code == 400
    resp = client.get("/api/fng/history?days=-5")
    assert resp.status_code == 400

    main_module.app.dependency_overrides.pop(main_module.get_fng_client, None)


def test_api_fng_history_uses_cache_when_refresh_recent(
    monkeypatch, TestingSessionLocal
):
    import backend.app.main as main_module
    from backend.app.core.settings import settings
    from backend.app.services.dao import FearGreedRepo, MetaRepo

    monkeypatch.setattr(settings, "REFRESH_GRANULARITY", "72h")

    session = TestingSessionLocal()
    repo = FearGreedRepo(session)
    meta_repo = MetaRepo(session)

    base = dt.datetime(2024, 5, 1, tzinfo=dt.timezone.utc)
    repo.upsert_many(
        [
            {
                "timestamp": base,
                "value": 15,
                "classification": "Fear",
                "ingested_at": base,
            },
            {
                "timestamp": base + dt.timedelta(days=1),
                "value": 45,
                "classification": "Neutral",
                "ingested_at": base + dt.timedelta(days=1),
            },
            {
                "timestamp": base + dt.timedelta(days=2),
                "value": 70,
                "classification": "Greed",
                "ingested_at": base + dt.timedelta(days=2),
            },
        ]
    )
    meta_repo.set(
        "fear_greed_last_refresh",
        (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=10)).isoformat(),
    )
    session.commit()

    def override_session():
        try:
            yield session
        finally:
            pass

    class StubClient:
        def get_latest(self, *args, **kwargs):  # pragma: no cover - should not run
            raise AssertionError("latest fetch should not execute when fresh")

        def get_historical(self, *args, **kwargs):  # pragma: no cover - should not run
            raise AssertionError("history fetch should not execute when fresh")

    main_module.app.dependency_overrides[main_module.get_session] = override_session
    main_module.app.dependency_overrides[main_module.get_fng_client] = lambda: StubClient()

    client = TestClient(main_module.app)
    resp = client.get("/api/fng/history?days=3")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["days"] == 3
    scores = [point["score"] for point in payload["points"]]
    assert scores == [15, 45, 70]
    labels = [point["label"] for point in payload["points"]]
    assert labels == ["Fear", "Neutral", "Greed"]

    main_module.app.dependency_overrides.pop(main_module.get_session, None)
    main_module.app.dependency_overrides.pop(main_module.get_fng_client, None)
    session.close()


def test_sync_fear_greed_index_skips_when_fresh(monkeypatch, TestingSessionLocal):
    from backend.app.services import fear_greed as service_module
    from backend.app.services.dao import MetaRepo, FearGreedRepo
    from backend.app.core.settings import settings

    monkeypatch.setattr(settings, "REFRESH_GRANULARITY", "6h")

    now = dt.datetime(2024, 1, 10, 12, 0, tzinfo=dt.timezone.utc)
    session = TestingSessionLocal()
    meta_repo = MetaRepo(session)
    repo = FearGreedRepo(session)
    repo.upsert_many(
        [
            {
                "timestamp": dt.datetime(2024, 1, 9, tzinfo=dt.timezone.utc),
                "value": 42,
                "classification": "Greed",
                "ingested_at": now - dt.timedelta(days=1),
            }
        ]
    )
    meta_repo.set(
        "fear_greed_last_refresh",
        (now - dt.timedelta(minutes=5)).isoformat(),
    )
    session.commit()
    session.close()

    class StubClient:
        def get_historical(self, **_: object):  # pragma: no cover - should skip
            raise AssertionError("history fetch should be skipped when fresh")

        def get_latest(self):  # pragma: no cover - should skip
            raise AssertionError("latest fetch should be skipped when fresh")

    new_session = TestingSessionLocal()
    try:
        processed = service_module.sync_fear_greed_index(
            session=new_session, client=StubClient(), now=now
        )
    finally:
        new_session.close()

    assert processed == 0


def test_sync_fear_greed_index_skips_history_when_multi_year_today_present(
    monkeypatch, TestingSessionLocal
):
    from backend.app.services import fear_greed as service_module
    from backend.app.services.dao import FearGreedRepo, MetaRepo
    from backend.app.core.settings import settings

    monkeypatch.setattr(settings, "REFRESH_GRANULARITY", "24h")

    now = dt.datetime(2024, 7, 1, 12, tzinfo=dt.timezone.utc)

    session = TestingSessionLocal()
    repo = FearGreedRepo(session)
    meta_repo = MetaRepo(session)

    repo.upsert_many(
        [
            {
                "timestamp": now - dt.timedelta(days=900),
                "value": 15,
                "classification": "Extreme Fear",
                "ingested_at": now - dt.timedelta(days=900),
            },
            {
                "timestamp": now - dt.timedelta(days=400),
                "value": 45,
                "classification": "Neutral",
                "ingested_at": now - dt.timedelta(days=400),
            },
            {
                "timestamp": dt.datetime(
                    now.year, now.month, now.day, tzinfo=dt.timezone.utc
                ),
                "value": 60,
                "classification": "Greed",
                "ingested_at": now - dt.timedelta(hours=1),
            },
        ]
    )
    meta_repo.set(
        "fear_greed_last_refresh",
        (now - dt.timedelta(days=3)).isoformat(),
    )
    session.commit()

    class StubClient:
        def get_historical(self, **_: object):  # pragma: no cover - should skip
            raise AssertionError("history fetch should be skipped when span is sufficient")

        def get_latest(self, **_: object):  # pragma: no cover - should skip
            raise AssertionError("latest fetch should be skipped when today is cached")

    try:
        processed = service_module.sync_fear_greed_index(
            session=session, client=StubClient(), now=now
        )
    finally:
        session.close()

    assert processed == 0


def test_sync_fear_greed_index_skips_when_cmc_budget_exhausted(
    TestingSessionLocal, tmp_path
):
    from backend.app.services import fear_greed as service_module
    now = dt.datetime(2024, 7, 1, 12, tzinfo=dt.timezone.utc)
    session = TestingSessionLocal()

    budget = CallBudget(tmp_path / "cmc_budget.json", quota=1)
    budget.spend(1, category="cmc_history")

    class StubClient:
        def __init__(self) -> None:
            self.history_calls = 0
            self.latest_calls = 0

        def get_historical(self, **_: object) -> list[dict]:
            self.history_calls += 1
            return []

        def get_latest(self) -> dict | None:
            self.latest_calls += 1
            return None

    stub = StubClient()
    try:
        processed = service_module.sync_fear_greed_index(
            session=session, client=stub, now=now, budget=budget
        )
    finally:
        session.close()

    assert processed == 0
    assert stub.history_calls == 0
    assert stub.latest_calls == 0


def test_sync_fear_greed_index_charges_history_budget_once_on_failure(
    monkeypatch, TestingSessionLocal, tmp_path
):
    from backend.app.services import fear_greed as service_module
    from backend.app.services.dao import FearGreedRepo, MetaRepo
    from backend.app.core.settings import settings

    monkeypatch.setattr(settings, "REFRESH_GRANULARITY", "24h")

    now = dt.datetime(2024, 7, 1, 12, tzinfo=dt.timezone.utc)

    session = TestingSessionLocal()
    repo = FearGreedRepo(session)
    meta_repo = MetaRepo(session)

    repo.upsert_many(
        [
            {
                "timestamp": dt.datetime(
                    now.year, now.month, now.day, tzinfo=dt.timezone.utc
                ),
                "value": 55,
                "classification": "Greed",
                "ingested_at": now - dt.timedelta(hours=1),
            }
        ]
    )
    meta_repo.set(
        "fear_greed_last_refresh",
        (now - dt.timedelta(days=3)).isoformat(),
    )
    session.commit()

    class StubClient:
        def get_historical(self, **_: object) -> list[dict]:
            raise requests.RequestException("history down")

        def get_latest(self) -> dict:  # pragma: no cover - guarded by has_today_value
            raise AssertionError(
                "latest fetch should be skipped when today's value is cached"
            )

    budget = CallBudget(tmp_path / "cmc_budget.json", quota=5)

    try:
        processed = service_module.sync_fear_greed_index(
            session=session, client=StubClient(), now=now, budget=budget
        )
    finally:
        session.close()

    assert processed == 0
    assert budget.monthly_call_count == 1
    assert budget.category_counts == {"cmc_history": 1}


def test_sync_fear_greed_index_fetches_latest_only_when_today_missing(
    monkeypatch, TestingSessionLocal
):
    from backend.app.services import fear_greed as service_module
    from backend.app.services.dao import FearGreedRepo, MetaRepo
    from backend.app.core.settings import settings

    monkeypatch.setattr(settings, "REFRESH_GRANULARITY", "24h")

    now = dt.datetime(2024, 7, 1, 12, tzinfo=dt.timezone.utc)

    session = TestingSessionLocal()
    repo = FearGreedRepo(session)
    meta_repo = MetaRepo(session)

    repo.upsert_many(
        [
            {
                "timestamp": now - dt.timedelta(days=800),
                "value": 20,
                "classification": "Extreme Fear",
                "ingested_at": now - dt.timedelta(days=800),
            },
            {
                "timestamp": now - dt.timedelta(days=300),
                "value": 40,
                "classification": "Fear",
                "ingested_at": now - dt.timedelta(days=300),
            },
            {
                "timestamp": dt.datetime(
                    2024, 6, 30, tzinfo=dt.timezone.utc
                ),
                "value": 55,
                "classification": "Greed",
                "ingested_at": now - dt.timedelta(days=1),
            },
        ]
    )
    meta_repo.set(
        "fear_greed_last_refresh",
        (now - dt.timedelta(days=3)).isoformat(),
    )
    session.commit()

    class StubClient:
        def __init__(self) -> None:
            self.latest_calls = 0

        def get_historical(self, **_: object):  # pragma: no cover - should skip
            raise AssertionError("history fetch should be skipped when multi-year data exists")

        def get_latest(self, **_: object):
            self.latest_calls += 1
            return {
                "timestamp": "2024-07-01T00:00:00Z",
                "score": 65,
                "label": "Greed",
            }

    try:
        processed = service_module.sync_fear_greed_index(
            session=session, client=StubClient(), now=now
        )
        latest = repo.get_latest()
        meta_value = meta_repo.get("fear_greed_last_refresh")
    finally:
        session.close()

    assert processed == 1
    assert latest is not None
    assert latest.timestamp.date() == now.date()
    assert latest.value == 65
    assert meta_value == now.isoformat()


def test_sync_fear_greed_index_ingests_unix_timestamps(
    monkeypatch, TestingSessionLocal
):
    from backend.app.services import fear_greed as service_module
    from backend.app.services.dao import FearGreedRepo, MetaRepo
    from backend.app.core.settings import settings

    monkeypatch.setattr(settings, "REFRESH_GRANULARITY", "24h")

    now = dt.datetime(2024, 9, 23, 12, tzinfo=dt.timezone.utc)
    latest_timestamp = dt.datetime(2024, 9, 23, tzinfo=dt.timezone.utc)
    history_timestamp = dt.datetime(2024, 9, 21, tzinfo=dt.timezone.utc)

    session = TestingSessionLocal()
    repo = FearGreedRepo(session)
    meta_repo = MetaRepo(session)

    class StubClient:
        def __init__(self) -> None:
            self.history_calls = 0

        def get_historical(self, **_: object) -> list[dict]:
            self.history_calls += 1
            return [
                {
                    "timestamp": history_timestamp.timestamp(),
                    "score": 30,
                    "label": "Fear",
                },
                {
                    "timestamp": latest_timestamp.timestamp(),
                    "score": 55.2,
                    "label": "Greed",
                },
            ]

        def get_latest(self) -> dict:  # pragma: no cover - should be skipped
            raise AssertionError("latest fetch should be skipped once today is ingested")

    stub = StubClient()

    try:
        processed = service_module.sync_fear_greed_index(
            session=session, client=stub, now=now
        )
        assert processed == 2
        assert stub.history_calls == 1

        latest = repo.get_latest()
        assert latest is not None
        assert latest.timestamp == latest_timestamp
        assert latest.value == 55
        assert latest.classification == "Greed"

        assert meta_repo.get("fear_greed_last_refresh") == now.isoformat()
    finally:
        session.close()


def test_sync_fear_greed_index_spends_budget_on_calls(
    TestingSessionLocal, tmp_path
):
    from backend.app.services import fear_greed as service_module

    now = dt.datetime(2024, 8, 1, 10, tzinfo=dt.timezone.utc)
    session = TestingSessionLocal()

    budget = CallBudget(tmp_path / "cmc_budget.json", quota=10)

    class StubClient:
        def __init__(self) -> None:
            self.history_calls = 0
            self.latest_calls = 0

        def get_historical(self, **_: object) -> list[dict]:
            self.history_calls += 1
            return [
                {
                    "timestamp": "2024-07-30T00:00:00Z",
                    "value": 40,
                    "value_classification": "Fear",
                }
            ]

        def get_latest(self) -> dict | None:
            self.latest_calls += 1
            return {
                "timestamp": "2024-08-01T00:00:00Z",
                "score": 55,
                "label": "Greed",
            }

    stub = StubClient()
    try:
        processed = service_module.sync_fear_greed_index(
            session=session, client=stub, now=now, budget=budget
        )
    finally:
        session.close()

    assert processed == 2
    assert stub.history_calls == 1
    assert stub.latest_calls == 1
    assert budget.monthly_call_count == 2
    assert budget.category_counts == {
        "cmc_history": 1,
        "cmc_latest": 1,
    }


def test_sync_fear_greed_index_fetches_history_when_span_insufficient(
    monkeypatch, TestingSessionLocal
):
    from backend.app.services import fear_greed as service_module
    from backend.app.services.dao import FearGreedRepo, MetaRepo
    from backend.app.core.settings import settings

    monkeypatch.setattr(settings, "REFRESH_GRANULARITY", "24h")

    now = dt.datetime(2024, 7, 1, 12, tzinfo=dt.timezone.utc)

    session = TestingSessionLocal()
    repo = FearGreedRepo(session)
    meta_repo = MetaRepo(session)

    repo.upsert_many(
        [
            {
                "timestamp": now - dt.timedelta(days=120),
                "value": 35,
                "classification": "Fear",
                "ingested_at": now - dt.timedelta(days=120),
            }
        ]
    )
    meta_repo.set(
        "fear_greed_last_refresh",
        (now - dt.timedelta(days=3)).isoformat(),
    )
    session.commit()

    class StubClient:
        def __init__(self) -> None:
            self.history_calls = 0
            self.latest_calls = 0

        def get_historical(self, **_: object):
            self.history_calls += 1
            return [
                {
                    "timestamp": "2024-06-29T00:00:00Z",
                    "score": 45,
                    "label": "Neutral",
                },
                {
                    "timestamp": "2024-06-30T00:00:00Z",
                    "score": 55,
                    "label": "Greed",
                },
            ]

        def get_latest(self, **_: object):
            self.latest_calls += 1
            return {
                "timestamp": "2024-07-01T00:00:00Z",
                "score": 60,
                "label": "Greed",
            }

    stub = StubClient()

    try:
        processed = service_module.sync_fear_greed_index(
            session=session, client=stub, now=now
        )
        count = repo.count()
        latest = repo.get_latest()
        meta_value = meta_repo.get("fear_greed_last_refresh")
    finally:
        session.close()

    assert stub.history_calls == 1
    assert stub.latest_calls == 1
    assert processed == 3
    assert count == 4
    assert latest is not None and latest.value == 60
    assert meta_value == now.isoformat()


def test_sync_fear_greed_index_updates_without_seed(TestingSessionLocal):
    class StubClient:
        def get_historical(self, limit=None):
            return [
                {
                    "timestamp": "2024-01-01T00:00:00Z",
                    "score": "60",
                    "label": "Greed",
                },
                {
                    "timestamp": "2024-01-02T00:00:00Z",
                    "score": 20,
                    "label": "",
                },
            ]

        def get_latest(self):
            return {
                "timestamp": "2024-01-03T00:00:00Z",
                "score": 50,
                "label": None,
            }

    session = TestingSessionLocal()
    from backend.app.services.dao import FearGreedRepo, MetaRepo
    from backend.app.services import fear_greed as service_module

    now = dt.datetime(2024, 1, 10, tzinfo=dt.timezone.utc)
    processed = service_module.sync_fear_greed_index(
        session=session,
        client=StubClient(),
        now=now,
    )
    session.commit()

    repo = FearGreedRepo(session)
    meta_repo = MetaRepo(session)
    assert repo.count() == 3
    latest = repo.get_latest()
    assert latest is not None and latest.value == 50
    assert latest.classification == "Indéterminé"
    history = repo.get_history()
    classifications = [row.classification for row in history]
    assert "Indéterminé" in classifications
    assert meta_repo.get("fear_greed_last_refresh") == now.isoformat()
    assert processed == 3

    session.close()
