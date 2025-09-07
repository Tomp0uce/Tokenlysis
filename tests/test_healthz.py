from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

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


def test_healthz_ready(monkeypatch, tmp_path):
    TestingSessionLocal = _setup_test_session(tmp_path)
    session = TestingSessionLocal()
    MetaRepo(session).set("bootstrap_done", "true")
    session.commit()
    session.close()

    import backend.app.main as main_module

    main_module.app.dependency_overrides[get_session] = lambda: TestingSessionLocal()
    client = TestClient(main_module.app)

    resp = client.get("/healthz")
    data = resp.json()
    assert resp.status_code == 200
    assert data["ready"] is True
    assert data["db_connected"] is True
    assert data["bootstrap_done"] is True


def test_healthz_not_bootstrapped(monkeypatch, tmp_path):
    TestingSessionLocal = _setup_test_session(tmp_path)

    import backend.app.main as main_module

    main_module.app.dependency_overrides[get_session] = lambda: TestingSessionLocal()
    client = TestClient(main_module.app)

    resp = client.get("/healthz")
    data = resp.json()
    assert resp.status_code == 200
    assert data["ready"] is False
    assert data["bootstrap_done"] is False


def test_healthz_db_error(monkeypatch):
    class BrokenSession:
        def execute(self, *_a, **_k):
            raise RuntimeError("boom")

        def close(self):
            pass

    def _broken_session():
        session = BrokenSession()
        try:
            yield session
        finally:
            session.close()

    import backend.app.main as main_module

    main_module.app.dependency_overrides[get_session] = _broken_session
    client = TestClient(main_module.app)

    resp = client.get("/healthz")
    data = resp.json()
    assert resp.status_code == 200
    assert data["ready"] is False
    assert data["db_connected"] is False
