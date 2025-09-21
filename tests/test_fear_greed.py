import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete
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


def test_parse_seed_file_normalizes_rows(tmp_path):
    sample = tmp_path / "seed.txt"
    sample.write_text(
        """Date Value Classification\n\n\n2018-02-02  12  Extreme Fear\n2018-02-01\t55\tGreed Rising\n2018-02-03 8\tFear\n""",
        encoding="utf-8",
    )

    from backend.app.seed import fear_greed as module

    rows = module.parse_seed_file(sample)
    assert [row["value"] for row in rows] == [55, 12, 8]
    assert [row["classification"] for row in rows] == [
        "Greed Rising",
        "Extreme Fear",
        "Fear",
    ]
    timestamps = [row["timestamp"] for row in rows]
    assert all(ts.tzinfo is dt.timezone.utc for ts in timestamps)
    assert timestamps == sorted(timestamps)


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


def test_api_latest_and_not_found(monkeypatch, TestingSessionLocal):
    import backend.app.main as main_module
    from backend.app.db import get_session
    from backend.app.models import FearGreed

    def override_session():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    main_module.app.dependency_overrides[get_session] = override_session

    session = TestingSessionLocal()
    ts = dt.datetime(2024, 2, 1, tzinfo=dt.timezone.utc)
    session.add(
        FearGreed(
            timestamp=ts,
            value=60,
            classification="Greed",
            ingested_at=ts,
        )
    )
    session.commit()
    session.close()

    client = TestClient(main_module.app)

    resp = client.get("/api/fear-greed/latest")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["value"] == 60
    assert payload["classification"] == "Greed"
    assert payload["timestamp"] == ts.isoformat()

    session = TestingSessionLocal()
    session.execute(delete(FearGreed))
    session.commit()
    session.close()

    resp = client.get("/api/fear-greed/latest")
    assert resp.status_code == 404

    main_module.app.dependency_overrides.pop(get_session, None)


def test_api_history_ranges_and_validation(monkeypatch, TestingSessionLocal):
    import backend.app.main as main_module
    from backend.app.db import get_session
    from backend.app.models import FearGreed

    def override_session():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    main_module.app.dependency_overrides[get_session] = override_session

    session = TestingSessionLocal()
    now = dt.datetime.now(dt.timezone.utc)
    entries = [
        FearGreed(
            timestamp=now - dt.timedelta(days=120),
            value=10,
            classification="Extreme Fear",
            ingested_at=now,
        ),
        FearGreed(
            timestamp=now - dt.timedelta(days=40),
            value=25,
            classification="Fear",
            ingested_at=now,
        ),
        FearGreed(
            timestamp=now - dt.timedelta(days=5),
            value=70,
            classification="Greed",
            ingested_at=now,
        ),
    ]
    session.add_all(entries)
    session.commit()
    session.close()

    client = TestClient(main_module.app)

    resp = client.get("/api/fear-greed/history?range=30d")
    assert resp.status_code == 200
    data = resp.json()
    assert data["range"] == "30d"
    assert len(data["points"]) == 1

    resp = client.get("/api/fear-greed/history?range=max")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["points"]) == 3

    resp = client.get("/api/fear-greed/history?range=oops")
    assert resp.status_code == 400

    main_module.app.dependency_overrides.pop(get_session, None)


def test_sync_fear_greed_index_loads_seed_and_updates(monkeypatch, tmp_path, TestingSessionLocal):
    seed_path = tmp_path / "fg_seed.txt"
    seed_path.write_text(
        "Date Value Classification\n2018-02-01 11 Extreme Fear\n",
        encoding="utf-8",
    )

    from backend.app.core import settings as settings_module

    monkeypatch.setattr(settings_module.settings, "FEAR_GREED_SEED_FILE", str(seed_path))

    class StubClient:
        def get_fear_greed_history(self):
            return [
                {
                    "timestamp": "2024-01-01T00:00:00Z",
                    "value": "60",
                    "value_classification": "Greed",
                },
                {
                    "timestamp": "2024-01-02T00:00:00Z",
                    "value": 20,
                    "value_classification": "",
                },
            ]

        def get_fear_greed_latest(self):
            return {
                "timestamp": "2024-01-03T00:00:00Z",
                "value": 50,
                "value_classification": None,
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
    assert repo.count() >= 3
    latest = repo.get_latest()
    assert latest is not None and latest.value == 50
    assert latest.classification == "Indéterminé"
    history = repo.get_history()
    classifications = [row.classification for row in history]
    assert "Indéterminé" in classifications
    assert meta_repo.get("fear_greed_last_refresh") == now.isoformat()
    assert processed >= 3

    session.close()
