from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import datetime as dt

from backend.app.db import Base, get_session
from backend.app.services.dao import MetaRepo


def _setup_test_session(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path/'test.db'}", connect_args={"check_same_thread": False}
    )
    TestingSessionLocal = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
    )
    Base.metadata.create_all(bind=engine)
    return TestingSessionLocal


def test_last_refresh_api_returns_timestamp(tmp_path):
    TestingSessionLocal = _setup_test_session(tmp_path)
    session = TestingSessionLocal()
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    MetaRepo(session).set("last_refresh_at", now)
    session.commit()
    session.close()

    import backend.app.main as main_module

    main_module.app.dependency_overrides[get_session] = lambda: TestingSessionLocal()
    client = TestClient(main_module.app)

    resp = client.get("/api/last-refresh")
    assert resp.status_code == 200
    assert resp.json() == {"last_refresh_at": now}


def test_last_refresh_api_returns_null_when_missing(tmp_path):
    TestingSessionLocal = _setup_test_session(tmp_path)

    import backend.app.main as main_module

    main_module.app.dependency_overrides[get_session] = lambda: TestingSessionLocal()
    client = TestClient(main_module.app)

    resp = client.get("/api/last-refresh")
    assert resp.status_code == 200
    assert resp.json() == {"last_refresh_at": None}
