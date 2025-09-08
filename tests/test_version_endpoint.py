from __future__ import annotations

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


def _make_client(monkeypatch, tmp_path):
    TestingSessionLocal = _setup_test_session(tmp_path)
    import backend.app.main as main_module

    monkeypatch.setattr(main_module, "run_etl", lambda *_, **__: 0)
    main_module.app.dependency_overrides[get_session] = lambda: TestingSessionLocal()
    client = TestClient(main_module.app)
    return client, main_module


def test_env_version(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_VERSION", "7.7.7")
    client, main_module = _make_client(monkeypatch, tmp_path)
    resp = client.get("/api/version")
    assert resp.status_code == 200
    assert resp.json() == {"version": "7.7.7"}
    main_module.app.dependency_overrides.clear()


def test_file_version(monkeypatch, tmp_path):
    monkeypatch.delenv("APP_VERSION", raising=False)
    monkeypatch.setattr(
        "backend.app.core.version.REPO_ROOT", tmp_path
    )
    (tmp_path / "VERSION").write_text("8.8.8")
    client, main_module = _make_client(monkeypatch, tmp_path)
    resp = client.get("/api/version")
    assert resp.status_code == 200
    assert resp.json() == {"version": "8.8.8"}
    main_module.app.dependency_overrides.clear()


def test_default_dev(monkeypatch, tmp_path):
    monkeypatch.delenv("APP_VERSION", raising=False)
    monkeypatch.setattr(
        "backend.app.core.version.REPO_ROOT", tmp_path
    )
    client, main_module = _make_client(monkeypatch, tmp_path)
    resp = client.get("/api/version")
    assert resp.status_code == 200
    assert resp.json() == {"version": "dev"}
    main_module.app.dependency_overrides.clear()
