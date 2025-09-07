import datetime as dt
import importlib

from fastapi.testclient import TestClient


def test_markets_top_reads_db(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path/'test.db'}")
    import backend.app.core.settings as settings_module

    importlib.reload(settings_module)
    import backend.app.db as db_module

    importlib.reload(db_module)
    import backend.app.models as models_module

    importlib.reload(models_module)
    from backend.app.db import Base, SessionLocal
    from backend.app.services.dao import PricesRepo, MetaRepo

    Base.metadata.create_all(bind=db_module.engine)
    session = SessionLocal()
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
    session.commit()
    session.close()

    import backend.app.main as main_module

    importlib.reload(main_module)
    client = TestClient(main_module.app)
    resp = client.get("/api/markets/top?limit=1&vs=usd")
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"][0]["coin_id"] == "bitcoin"
    assert data["data_source"] == "api"
