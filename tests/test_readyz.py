from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.db import Base, get_session


def _setup_test_session(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path/'test.db'}", connect_args={"check_same_thread": False}
    )
    TestingSessionLocal = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
    )
    Base.metadata.create_all(bind=engine)
    return TestingSessionLocal


def test_readyz_ok(monkeypatch, tmp_path):
    TestingSessionLocal = _setup_test_session(tmp_path)

    import backend.app.main as main_module

    main_module.app.dependency_overrides[get_session] = lambda: TestingSessionLocal()
    client = TestClient(main_module.app)

    resp = client.get("/readyz")
    assert resp.status_code == 200
    assert resp.json() == {"ready": True}


def test_readyz_db_error(monkeypatch, tmp_path):
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

    resp = client.get("/readyz")
    assert resp.status_code == 503


def test_frontend_served(monkeypatch, tmp_path):
    TestingSessionLocal = _setup_test_session(tmp_path)
    import backend.app.main as main_module

    main_module.app.dependency_overrides[get_session] = lambda: TestingSessionLocal()
    client = TestClient(main_module.app)

    resp = client.get("/")
    assert resp.status_code == 200
    assert "<!DOCTYPE html>" in resp.text


def test_frontend_missing_file(monkeypatch, tmp_path):
    TestingSessionLocal = _setup_test_session(tmp_path)
    import backend.app.main as main_module

    main_module.app.dependency_overrides[get_session] = lambda: TestingSessionLocal()
    client = TestClient(main_module.app)

    resp = client.get("/no-such-file")
    assert resp.status_code == 404
