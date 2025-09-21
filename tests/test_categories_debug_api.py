import datetime as dt
import json

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.db import Base, get_session
from backend.app.models import Coin
from backend.app.services.dao import CoinsRepo


def _setup_test_session(tmp_path) -> sessionmaker:
    engine = create_engine(
        f"sqlite:///{tmp_path/'categories.db'}", connect_args={"check_same_thread": False}
    )
    TestingSessionLocal = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
    )
    Base.metadata.create_all(bind=engine)
    return TestingSessionLocal


def _add_coin(
    session,
    *,
    coin_id: str,
    category_names: list[str] | None,
    updated_at: dt.datetime | None,
) -> None:
    session.add(
        Coin(
            id=coin_id,
            symbol=coin_id.upper(),
            name=coin_id.title(),
            category_names=None if category_names is None else json.dumps(category_names),
            category_ids=json.dumps([f"{coin_id}-cat"]),
            updated_at=updated_at,
        )
    )


def test_list_category_issues_flags_missing_and_stale(tmp_path):
    TestingSessionLocal = _setup_test_session(tmp_path)
    session = TestingSessionLocal()
    now = dt.datetime(2025, 2, 1, 12, 0, tzinfo=dt.timezone.utc)

    _add_coin(session, coin_id="fresh", category_names=["defi"], updated_at=now - dt.timedelta(hours=6))
    _add_coin(session, coin_id="missing_null", category_names=None, updated_at=now - dt.timedelta(hours=1))
    _add_coin(session, coin_id="missing_empty", category_names=[], updated_at=now - dt.timedelta(hours=2))
    _add_coin(session, coin_id="stale_old", category_names=["defi"], updated_at=now - dt.timedelta(hours=72))
    _add_coin(session, coin_id="stale_unknown", category_names=["defi"], updated_at=None)
    _add_coin(
        session,
        coin_id="missing_and_stale",
        category_names=None,
        updated_at=now - dt.timedelta(days=3),
    )

    session.commit()

    repo = CoinsRepo(session)
    issues = repo.list_category_issues(now=now, stale_after=dt.timedelta(hours=24))

    issues_by_id = {item["coin_id"]: item for item in issues}

    assert "fresh" not in issues_by_id
    assert issues_by_id["missing_null"]["reasons"] == ["missing_categories"]
    assert issues_by_id["missing_empty"]["reasons"] == ["missing_categories"]
    assert issues_by_id["stale_old"]["reasons"] == ["stale_timestamp"]
    assert issues_by_id["stale_unknown"]["reasons"] == ["stale_timestamp"]
    assert issues_by_id["missing_and_stale"]["reasons"] == [
        "missing_categories",
        "stale_timestamp",
    ]

    assert issues_by_id["missing_null"]["updated_at"] == now - dt.timedelta(hours=1)
    assert issues_by_id["stale_unknown"]["updated_at"] is None


def test_debug_categories_endpoint_reports_payload(monkeypatch, tmp_path):
    TestingSessionLocal = _setup_test_session(tmp_path)
    session = TestingSessionLocal()
    now = dt.datetime(2025, 2, 1, 12, 0, tzinfo=dt.timezone.utc)

    _add_coin(session, coin_id="fresh", category_names=["defi"], updated_at=now - dt.timedelta(hours=6))
    _add_coin(session, coin_id="missing", category_names=None, updated_at=now - dt.timedelta(hours=1))
    session.commit()
    session.close()

    import backend.app.main as main_module

    class _FixedDateTime(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return now.replace(tzinfo=None)
            return now.astimezone(tz)

    monkeypatch.setattr(main_module.dt, "datetime", _FixedDateTime)

    dependency_overrides = main_module.app.dependency_overrides
    dependency_overrides[get_session] = lambda: TestingSessionLocal()

    client = TestClient(main_module.app)
    try:
        response = client.get("/api/debug/categories")
    finally:
        dependency_overrides.pop(get_session, None)

    assert response.status_code == 200
    data = response.json()
    assert data["generated_at"] == now.isoformat()
    assert data["stale_after_hours"] == 24
    assert data["items"]
    assert data["items"][0]["coin_id"] == "missing"
    assert data["items"][0]["reasons"] == ["missing_categories"]
