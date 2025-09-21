import datetime as dt
from collections.abc import Iterable

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.db import Base, get_session
from backend.app.models import LatestPrice, Price


def _setup_test_session(tmp_path) -> sessionmaker:
    engine = create_engine(
        f"sqlite:///{tmp_path/'test.db'}", connect_args={"check_same_thread": False}
    )
    TestingSessionLocal = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
    )
    Base.metadata.create_all(bind=engine)
    return TestingSessionLocal


def _insert_history(
    session,
    *,
    coin_id: str,
    timestamps: Iterable[dt.datetime],
    vs_currency: str = "usd",
) -> None:
    for ts in timestamps:
        session.add(
            Price(
                coin_id=coin_id,
                vs_currency=vs_currency,
                snapshot_at=ts,
            )
        )


def test_history_gaps_flags_incomplete_coins(monkeypatch, tmp_path):
    TestingSessionLocal = _setup_test_session(tmp_path)
    session = TestingSessionLocal()
    now = dt.datetime(2025, 1, 8, 12, 0, tzinfo=dt.timezone.utc)

    session.add_all(
        [
            LatestPrice(
                coin_id="bitcoin",
                vs_currency="usd",
                rank=1,
                snapshot_at=now,
            ),
            LatestPrice(
                coin_id="ethereum",
                vs_currency="usd",
                rank=2,
                snapshot_at=now,
            ),
            LatestPrice(
                coin_id="litecoin",
                vs_currency="usd",
                rank=3,
                snapshot_at=now,
            ),
        ]
    )

    def _timestamps(count: int) -> list[dt.datetime]:
        return [now - dt.timedelta(hours=12 * i) for i in range(count)]

    _insert_history(session, coin_id="bitcoin", timestamps=_timestamps(14))
    _insert_history(session, coin_id="ethereum", timestamps=_timestamps(9))

    session.commit()
    session.close()

    import backend.app.main as main_module

    monkeypatch.setattr(
        main_module,
        "RANGE_TO_DELTA",
        {
            "24h": dt.timedelta(hours=24),
            "7d": dt.timedelta(days=7),
        },
    )

    class _FixedDateTime(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return now.replace(tzinfo=None)
            return now.astimezone(tz)

        @classmethod
        def utcnow(cls):
            return now.replace(tzinfo=None)

    monkeypatch.setattr(main_module.dt, "datetime", _FixedDateTime)
    dependency_overrides = main_module.app.dependency_overrides
    dependency_overrides[get_session] = lambda: TestingSessionLocal()

    client = TestClient(main_module.app)
    try:
        response = client.get("/api/debug/history-gaps")
    finally:
        dependency_overrides.pop(get_session, None)

    assert response.status_code == 200
    data = response.json()
    assert data["granularity"] == "12h"
    assert data["vs_currency"] == "usd"
    assert data["generated_at"] == now.isoformat()

    items = {item["coin_id"]: item for item in data["items"]}
    assert "bitcoin" not in items
    assert items["ethereum"]["ranges"] == {
        "7d": {"expected": 14, "actual": 9, "missing": 5}
    }
    assert items["litecoin"]["ranges"] == {
        "24h": {"expected": 2, "actual": 0, "missing": 2},
        "7d": {"expected": 14, "actual": 0, "missing": 14},
    }
