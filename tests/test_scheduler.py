import asyncio
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.db import Base
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


def test_startup_runs_etl_when_not_bootstrapped(monkeypatch, tmp_path):
    TestingSessionLocal = _setup_test_session(tmp_path)

    def _session_override():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    import backend.app.main as main_module

    monkeypatch.setattr(main_module, "get_session", _session_override)
    monkeypatch.setattr(main_module.asyncio, "create_task", lambda coro: coro.close())
    called = {"etl": 0, "seed": 0}

    def fake_run_etl(*_a, **_k):
        called["etl"] += 1

    def fake_load_seed():
        called["seed"] += 1

    monkeypatch.setattr(main_module, "run_etl", fake_run_etl)
    monkeypatch.setattr(main_module, "load_seed", fake_load_seed)

    asyncio.run(main_module.startup())

    assert called["etl"] == 1
    assert called["seed"] == 0


def test_startup_loads_seed_when_bootstrapped(monkeypatch, tmp_path):
    TestingSessionLocal = _setup_test_session(tmp_path)
    session = TestingSessionLocal()
    MetaRepo(session).set("bootstrap_done", "true")
    session.commit()
    session.close()

    def _session_override():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    import backend.app.main as main_module

    monkeypatch.setattr(main_module, "get_session", _session_override)
    monkeypatch.setattr(main_module.asyncio, "create_task", lambda coro: coro.close())
    called = {"etl": 0, "seed": 0}

    def fake_run_etl(*_a, **_k):
        called["etl"] += 1

    def fake_load_seed():
        called["seed"] += 1

    monkeypatch.setattr(main_module, "run_etl", fake_run_etl)
    monkeypatch.setattr(main_module, "load_seed", fake_load_seed)

    asyncio.run(main_module.startup())

    assert called["etl"] == 0
    assert called["seed"] == 1


def test_scheduler_waits_between_runs(monkeypatch, tmp_path):
    TestingSessionLocal = _setup_test_session(tmp_path)
    session = TestingSessionLocal()
    MetaRepo(session).set("bootstrap_done", "true")
    session.commit()
    session.close()

    def _session_override():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    import backend.app.main as main_module

    monkeypatch.setattr(main_module, "get_session", _session_override)

    run_calls = []
    sleep_args = []

    def fake_run_etl(*_a, **_k):
        run_calls.append(1)

    async def fake_sleep(seconds):
        sleep_args.append(seconds)
        raise RuntimeError

    tasks = []

    def fake_create_task(coro):
        tasks.append(coro)
        return None

    monkeypatch.setattr(main_module, "run_etl", fake_run_etl)
    monkeypatch.setattr(main_module, "load_seed", lambda: None)
    monkeypatch.setattr(main_module.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(main_module.asyncio, "create_task", fake_create_task)

    asyncio.run(main_module.startup())
    assert len(tasks) == 1
    with pytest.raises(RuntimeError):
        asyncio.run(tasks[0])
    assert run_calls == [1]
    assert sleep_args == [main_module.refresh_interval_seconds()]


def test_scheduler_reschedules_on_granularity_change(monkeypatch):
    import backend.app.main as main_module
    from backend.app.core.settings import settings

    sleep_calls: list[int] = []

    async def fake_sleep(seconds):
        sleep_calls.append(seconds)
        if len(sleep_calls) == 1:
            settings.REFRESH_GRANULARITY = "1h"
            return
        raise RuntimeError

    monkeypatch.setattr(main_module.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(main_module, "run_etl", lambda *_a, **_k: None)

    orig = settings.REFRESH_GRANULARITY
    settings.REFRESH_GRANULARITY = "2h"
    with pytest.raises(RuntimeError):
        asyncio.run(main_module.etl_loop())
    assert sleep_calls == [2 * 60 * 60, 1 * 60 * 60]
    settings.REFRESH_GRANULARITY = orig
