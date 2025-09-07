import datetime as dt

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.db import Base, get_session
from backend.app.services.dao import PricesRepo, MetaRepo


def test_markets_top_reads_db_and_stale_flag(monkeypatch, tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path/'test.db'}", connect_args={"check_same_thread": False}
    )
    TestingSessionLocal = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
    )
    Base.metadata.create_all(bind=engine)

    session = TestingSessionLocal()
    prices_repo = PricesRepo(session)
    meta_repo = MetaRepo(session)
    now = dt.datetime.now(dt.timezone.utc)
    prices_repo.upsert_latest(
        [
            {
                "coin_id": "bitcoin",
                "vs_currency": "usd",
                "price": 1.0,
                "market_cap": 1.0,
                "volume_24h": 1.0,
                "rank": 1,
                "pct_change_24h": 0.0,
                "snapshot_at": now,
            }
        ]
    )
    meta_repo.set("last_refresh_at", now.isoformat())
    meta_repo.set("data_source", "api")
    meta_repo.set("bootstrap_done", "true")
    session.commit()
    session.close()

    import backend.app.main as main_module

    def _fail(*_a, **_k):
        raise AssertionError("run_etl should not be called")

    monkeypatch.setattr(main_module, "run_etl", _fail)
    main_module.app.dependency_overrides[get_session] = lambda: TestingSessionLocal()
    main_module.app.router.on_startup = []
    main_module.app.router.on_shutdown = []

    client = TestClient(main_module.app)
    resp = client.get("/api/markets/top?limit=1&vs=usd")
    data = resp.json()
    assert data["items"][0]["coin_id"] == "bitcoin"
    assert data["data_source"] == "api"
    assert data["stale"] is False

    # Mark data as stale
    session = TestingSessionLocal()
    meta_repo = MetaRepo(session)
    old = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=25)).isoformat()
    meta_repo.set("last_refresh_at", old)
    session.commit()
    session.close()

    resp = client.get("/api/markets/top?limit=1&vs=usd")
    assert resp.json()["stale"] is True
