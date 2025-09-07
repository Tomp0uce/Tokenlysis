from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.core.version import get_version
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


def test_version_from_env(monkeypatch, tmp_path):
    TestingSessionLocal = _setup_test_session(tmp_path)
    monkeypatch.setenv("APP_VERSION", "1.2.3")
    import backend.app.main as main_module

    monkeypatch.setattr(main_module, "run_etl", lambda *_, **__: 0)
    main_module.app.dependency_overrides[get_session] = lambda: TestingSessionLocal()
    client = TestClient(main_module.app)

    expected = get_version()
    resp = client.get("/version")
    assert resp.status_code == 200
    assert resp.json() == {"version": expected}

    main_module.app.dependency_overrides.clear()


def test_version_fallback(monkeypatch, tmp_path):
    TestingSessionLocal = _setup_test_session(tmp_path)
    monkeypatch.setenv("APP_VERSION", "dev")
    import backend.app.main as main_module

    monkeypatch.setattr(main_module, "run_etl", lambda *_, **__: 0)
    main_module.app.dependency_overrides[get_session] = lambda: TestingSessionLocal()
    client = TestClient(main_module.app)

    expected = get_version()
    resp = client.get("/api/version")
    assert resp.status_code == 200
    assert resp.json() == {"version": expected}

    main_module.app.dependency_overrides.clear()
