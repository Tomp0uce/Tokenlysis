import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import backend.app.main as main_module
from backend.app.db import Base, get_session
from backend.app.models import Price


def _setup_session(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path/'test.db'}", connect_args={"check_same_thread": False}
    )
    TestingSessionLocal = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
    )
    Base.metadata.create_all(bind=engine)
    return TestingSessionLocal


def _insert_price(
    session,
    coin_id: str,
    vs: str,
    snapshot_at: dt.datetime,
    *,
    price: float | None = None,
    market_cap: float | None = None,
    volume_24h: float | None = None,
) -> None:
    session.add(
        Price(
            coin_id=coin_id,
            vs_currency=vs,
            snapshot_at=snapshot_at,
            price=price,
            market_cap=market_cap,
            volume_24h=volume_24h,
        )
    )


def test_price_history_returns_points_within_range(tmp_path):
    TestingSessionLocal = _setup_session(tmp_path)
    session = TestingSessionLocal()
    now = dt.datetime.now(dt.timezone.utc)
    _insert_price(
        session,
        'bitcoin',
        'usd',
        now - dt.timedelta(days=2),
        price=1.0,
        market_cap=10.0,
        volume_24h=5.0,
    )
    _insert_price(
        session,
        'bitcoin',
        'usd',
        now - dt.timedelta(days=8),
        price=2.0,
        market_cap=20.0,
        volume_24h=6.0,
    )
    _insert_price(
        session,
        'bitcoin',
        'usd',
        now - dt.timedelta(hours=6),
        price=3.0,
        market_cap=30.0,
        volume_24h=7.0,
    )
    session.commit()
    session.close()

    main_module.app.dependency_overrides[get_session] = lambda: TestingSessionLocal()
    client = TestClient(main_module.app)
    resp = client.get('/api/price/bitcoin/history?range=7d&vs=usd')
    assert resp.status_code == 200
    data = resp.json()
    assert data['coin_id'] == 'bitcoin'
    assert data['range'] == '7d'
    assert len(data['points']) == 2
    snapshots = [dt.datetime.fromisoformat(pt['snapshot_at']) for pt in data['points']]
    assert snapshots == sorted(snapshots)
    assert data['points'][0]['price'] == 1.0
    assert data['points'][1]['price'] == 3.0
    assert data['points'][0]['market_cap'] == 10.0
    assert data['points'][1]['volume_24h'] == 7.0


def test_price_history_max_range_returns_all(tmp_path):
    TestingSessionLocal = _setup_session(tmp_path)
    session = TestingSessionLocal()
    now = dt.datetime.now(dt.timezone.utc)
    _insert_price(
        session,
        'bitcoin',
        'usd',
        now - dt.timedelta(days=120),
        price=1.0,
        market_cap=2.0,
        volume_24h=3.0,
    )
    _insert_price(
        session,
        'bitcoin',
        'usd',
        now - dt.timedelta(days=1),
        price=4.0,
        market_cap=5.0,
        volume_24h=6.0,
    )
    session.commit()
    session.close()

    main_module.app.dependency_overrides[get_session] = lambda: TestingSessionLocal()
    client = TestClient(main_module.app)
    resp = client.get('/api/price/bitcoin/history?range=max&vs=usd')
    assert resp.status_code == 200
    data = resp.json()
    assert len(data['points']) == 2


def test_price_history_rejects_invalid_range(tmp_path):
    TestingSessionLocal = _setup_session(tmp_path)
    main_module.app.dependency_overrides[get_session] = lambda: TestingSessionLocal()
    client = TestClient(main_module.app)
    resp = client.get('/api/price/bitcoin/history?range=42d&vs=usd')
    assert resp.status_code == 400
    assert resp.json()['detail'] == 'unsupported range'


@pytest.fixture(autouse=True)
def cleanup_dependency_overrides():
    yield
    main_module.app.dependency_overrides.clear()
