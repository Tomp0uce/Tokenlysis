import datetime as dt

import pytest
import requests
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


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


@pytest.fixture()
def db_session(TestingSessionLocal):
    session_factory = TestingSessionLocal
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


def test_fear_greed_repo_upsert_and_history(TestingSessionLocal):
    from backend.app.services.dao import FearGreedRepo
    from backend.app.models import FearGreed

    session_factory = TestingSessionLocal
    session = session_factory()
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


def test_api_fng_latest_success(monkeypatch, db_session):
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

    session = db_session

    def override_session():
        try:
            yield session
        finally:
            pass

    stub = StubClient()
    main_module.app.dependency_overrides[main_module.get_session] = override_session
    main_module.app.dependency_overrides[main_module.get_fng_client] = lambda: stub

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
    assert stub.history_calls == []

    main_module.app.dependency_overrides.pop(main_module.get_session, None)
    main_module.app.dependency_overrides.pop(main_module.get_fng_client, None)


def test_api_fng_latest_falls_back_to_history(monkeypatch, db_session):
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

    session = db_session

    def override_session():
        try:
            yield session
        finally:
            pass

    stub = StubClient()
    main_module.app.dependency_overrides[main_module.get_session] = override_session
    main_module.app.dependency_overrides[main_module.get_fng_client] = lambda: stub

    client = TestClient(main_module.app)
    resp = client.get("/api/fng/latest")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["score"] == 35
    assert payload["label"] == "Neutral"
    assert payload["timestamp"].startswith("2024-03-11")
    assert stub.history_calls == [
        {"limit": 1, "time_start": None, "time_end": None}
    ]

    main_module.app.dependency_overrides.pop(main_module.get_session, None)
    main_module.app.dependency_overrides.pop(main_module.get_fng_client, None)


def test_api_fng_latest_uses_database_fallback(monkeypatch, db_session):
    import backend.app.main as main_module

    class StubClient:
        def get_latest(self) -> dict:
            raise requests.RequestException("down")

        def get_historical(self, **_: object) -> list[dict]:
            raise requests.RequestException("down history")

    session = db_session
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

    client = TestClient(main_module.app)
    resp = client.get("/api/fng/latest")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["score"] == 42
    assert payload["label"] == "Greed"
    assert payload["timestamp"].startswith("2024-04-01")

    main_module.app.dependency_overrides.pop(main_module.get_session, None)
    main_module.app.dependency_overrides.pop(main_module.get_fng_client, None)


def test_api_fng_latest_prefers_database_without_api_call(
    monkeypatch, db_session
):
    import backend.app.main as main_module

    class StubClient:
        def get_latest(self) -> dict:
            raise AssertionError("should not call get_latest when database has data")

        def get_historical(self, **_: object) -> list[dict]:
            raise AssertionError("should not call get_historical when database has data")

    session = db_session
    from backend.app.services.dao import FearGreedRepo

    repo = FearGreedRepo(session)
    ts = dt.datetime(2024, 4, 2, tzinfo=dt.timezone.utc)
    repo.upsert_many(
        [
            {
                "timestamp": ts,
                "value": 60,
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

    client = TestClient(main_module.app)
    resp = client.get("/api/fng/latest")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["score"] == 60
    assert payload["label"] == "Greed"
    assert payload["timestamp"].startswith("2024-04-02")

    main_module.app.dependency_overrides.pop(main_module.get_session, None)
    main_module.app.dependency_overrides.pop(main_module.get_fng_client, None)


def test_api_fng_latest_propagates_errors(monkeypatch, db_session):
    import backend.app.main as main_module

    class StubClient:
        def get_latest(self) -> dict:
            raise requests.RequestException("fail latest")

        def get_historical(self, **_: object) -> list[dict]:
            raise requests.RequestException("fail history")

    session = db_session

    def override_session():
        try:
            yield session
        finally:
            pass

    stub = StubClient()
    main_module.app.dependency_overrides[main_module.get_session] = override_session
    main_module.app.dependency_overrides[main_module.get_fng_client] = lambda: stub

    client = TestClient(main_module.app)
    resp = client.get("/api/fng/latest")
    assert resp.status_code == 502
    payload = resp.json()
    assert "fear & greed" in payload.get("detail", "").lower()

    main_module.app.dependency_overrides.pop(main_module.get_session, None)
    main_module.app.dependency_overrides.pop(main_module.get_fng_client, None)


def test_api_fng_history_orders_points(monkeypatch, db_session):
    import backend.app.main as main_module

    class StubClient:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def get_latest(self) -> dict:
            raise AssertionError("should not fetch latest")

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

    session = db_session

    def override_session():
        try:
            yield session
        finally:
            pass

    stub = StubClient()
    main_module.app.dependency_overrides[main_module.get_session] = override_session
    main_module.app.dependency_overrides[main_module.get_fng_client] = lambda: stub

    client = TestClient(main_module.app)
    resp = client.get("/api/fng/history?days=5")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["days"] == 5
    assert [point["score"] for point in payload["points"]] == [25, 55]
    assert stub.calls == [
        {"limit": 5, "time_start": None, "time_end": None}
    ]

    main_module.app.dependency_overrides.pop(main_module.get_session, None)
    main_module.app.dependency_overrides.pop(main_module.get_fng_client, None)


def test_api_fng_history_uses_database_fallback(monkeypatch, db_session):
    import backend.app.main as main_module

    class StubClient:
        def get_historical(self, **_: object) -> list[dict]:
            raise requests.RequestException("history offline")

        def get_latest(self) -> dict:
            raise AssertionError("should not call latest")

    session = db_session
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


def test_api_fng_history_prefers_database_without_api_call(
    monkeypatch, db_session
):
    import backend.app.main as main_module

    class StubClient:
        def get_historical(self, **_: object) -> list[dict]:
            raise AssertionError("should not call get_historical when database has data")

        def get_latest(self) -> dict:
            raise AssertionError("should not call get_latest when database has data")

    session = db_session
    from backend.app.services.dao import FearGreedRepo

    repo = FearGreedRepo(session)
    ts1 = dt.datetime(2024, 5, 1, tzinfo=dt.timezone.utc)
    ts2 = dt.datetime(2024, 5, 2, tzinfo=dt.timezone.utc)
    repo.upsert_many(
        [
            {
                "timestamp": ts1,
                "value": 30,
                "classification": "Fear",
                "ingested_at": ts2,
            },
            {
                "timestamp": ts2,
                "value": 45,
                "classification": "Neutral",
                "ingested_at": ts2,
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
    assert [point["score"] for point in payload["points"]] == [30, 45]
    assert payload["points"][0]["timestamp"].startswith("2024-05-01")
    assert payload["points"][1]["label"] == "Neutral"

    main_module.app.dependency_overrides.pop(main_module.get_session, None)
    main_module.app.dependency_overrides.pop(main_module.get_fng_client, None)


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

    session_factory = TestingSessionLocal
    session = session_factory()
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


def test_sync_fear_greed_index_skips_when_recent(monkeypatch, TestingSessionLocal):
    session_factory = TestingSessionLocal
    session = session_factory()
    from backend.app.services.dao import MetaRepo, FearGreedRepo
    from backend.app.services import fear_greed as service_module

    base_now = dt.datetime(2024, 5, 1, tzinfo=dt.timezone.utc)
    meta_repo = MetaRepo(session)
    meta_repo.set("fear_greed_last_refresh", (base_now - dt.timedelta(hours=1)).isoformat())
    session.commit()

    class GuardClient:
        def get_historical(self, *_, **__):  # pragma: no cover - should skip
            raise AssertionError("history call should be skipped when data is fresh")

        def get_latest(self, *_, **__):  # pragma: no cover - should skip
            raise AssertionError("latest call should be skipped when data is fresh")

    orig_granularity = service_module.settings.REFRESH_GRANULARITY
    monkeypatch.setattr(service_module.settings, "REFRESH_GRANULARITY", "12h")
    try:
        processed = service_module.sync_fear_greed_index(
            session=session,
            client=GuardClient(),
            now=base_now,
        )
    finally:
        monkeypatch.setattr(service_module.settings, "REFRESH_GRANULARITY", orig_granularity)

    assert processed == 0
    repo = FearGreedRepo(session)
    assert repo.count() == 0
    assert meta_repo.get("fear_greed_last_refresh") == (base_now - dt.timedelta(hours=1)).isoformat()
    session.close()
