import asyncio
import datetime as dt
import logging
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.db import Base
from backend.app.models import LatestPrice
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


def test_startup_runs_etl_when_not_bootstrapped(monkeypatch, tmp_path, caplog):
    TestingSessionLocal = _setup_test_session(tmp_path)

    def _session_override():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    import backend.app.main as main_module

    caplog.set_level(logging.INFO, logger="backend.app.main")
    monkeypatch.setattr(main_module.logging, "basicConfig", lambda **_k: None)
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
    assert any("startup path: ETL" in r.message for r in caplog.records)


def test_startup_skips_when_bootstrapped_and_has_data(monkeypatch, tmp_path, caplog):
    TestingSessionLocal = _setup_test_session(tmp_path)
    session = TestingSessionLocal()
    MetaRepo(session).set("bootstrap_done", "true")
    session.add(
        LatestPrice(
            coin_id="bitcoin",
            vs_currency="usd",
            price=1.0,
            market_cap=1.0,
            volume_24h=1.0,
            rank=1,
            pct_change_24h=0.0,
            snapshot_at=dt.datetime.now(dt.timezone.utc),
        )
    )
    session.commit()
    session.close()

    def _session_override():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    import backend.app.main as main_module

    caplog.set_level(logging.INFO, logger="backend.app.main")
    monkeypatch.setattr(main_module.logging, "basicConfig", lambda **_k: None)
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
    assert called["seed"] == 0
    assert any("startup path: skip" in r.message for r in caplog.records)


def test_startup_handles_missing_seed_when_etl_fails(monkeypatch, tmp_path, caplog):
    TestingSessionLocal = _setup_test_session(tmp_path)

    def _session_override():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    import backend.app.main as main_module
    from backend.app.core.settings import settings
    import backend.app.etl.run as run_module

    caplog.set_level(logging.INFO, logger="backend.app.main")
    monkeypatch.setattr(main_module.logging, "basicConfig", lambda **_k: None)
    monkeypatch.setattr(main_module, "get_session", _session_override)
    monkeypatch.setattr(main_module.asyncio, "create_task", lambda coro: coro.close())

    seed_calls = {"count": 0}

    def fake_run_etl(*_a, **_k):
        raise main_module.DataUnavailable

    def fake_load_seed():
        seed_calls["count"] += 1
        run_module.load_seed()

    monkeypatch.setattr(main_module, "run_etl", fake_run_etl)
    monkeypatch.setattr(main_module, "load_seed", fake_load_seed)
    monkeypatch.setattr(settings, "SEED_FILE", str(tmp_path / "missing.json"))

    asyncio.run(main_module.startup())

    assert seed_calls["count"] == 1
    session = TestingSessionLocal()
    assert MetaRepo(session).get("bootstrap_done") == "true"
    session.close()
    assert any("startup path: seed" in r.message for r in caplog.records)


def test_startup_bootstrapped_empty_table_runs_etl(monkeypatch, tmp_path, caplog):
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

    caplog.set_level(logging.INFO, logger="backend.app.main")
    monkeypatch.setattr(main_module.logging, "basicConfig", lambda **_k: None)
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
    assert any("startup path: ETL" in r.message for r in caplog.records)


def test_startup_bootstrapped_empty_table_etl_fails_uses_seed(
    monkeypatch, tmp_path, caplog
):
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

    caplog.set_level(logging.INFO, logger="backend.app.main")
    monkeypatch.setattr(main_module.logging, "basicConfig", lambda **_k: None)
    monkeypatch.setattr(main_module, "get_session", _session_override)
    monkeypatch.setattr(main_module.asyncio, "create_task", lambda coro: coro.close())

    called = {"etl": 0, "seed": 0}

    def fake_run_etl(*_a, **_k):
        called["etl"] += 1
        raise main_module.DataUnavailable

    def fake_load_seed():
        called["seed"] += 1

    monkeypatch.setattr(main_module, "run_etl", fake_run_etl)
    monkeypatch.setattr(main_module, "load_seed", fake_load_seed)

    asyncio.run(main_module.startup())

    assert called["etl"] == 1
    assert called["seed"] == 1
    assert any("startup path: seed" in r.message for r in caplog.records)


def test_scheduler_waits_between_runs(monkeypatch, tmp_path):
    TestingSessionLocal = _setup_test_session(tmp_path)
    session = TestingSessionLocal()
    MetaRepo(session).set("bootstrap_done", "true")
    session.add(
        LatestPrice(
            coin_id="bitcoin",
            vs_currency="usd",
            price=1.0,
            market_cap=1.0,
            volume_24h=1.0,
            rank=1,
            pct_change_24h=0.0,
            snapshot_at=dt.datetime.now(dt.timezone.utc),
        )
    )
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


def test_startup_creates_budget_dir(monkeypatch, tmp_path):
    TestingSessionLocal = _setup_test_session(tmp_path)

    def _session_override():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    import backend.app.main as main_module
    from backend.app.core.settings import settings

    monkeypatch.setattr(main_module.logging, "basicConfig", lambda **_k: None)
    monkeypatch.setattr(main_module, "get_session", _session_override)
    monkeypatch.setattr(main_module, "run_etl", lambda *_a, **_k: None)
    monkeypatch.setattr(main_module, "load_seed", lambda: None)
    monkeypatch.setattr(main_module.asyncio, "create_task", lambda coro: coro.close())

    path = tmp_path / "meta" / "budget.json"
    monkeypatch.setattr(settings, "BUDGET_FILE", str(path))

    asyncio.run(main_module.startup())

    assert path.parent.exists()
    assert main_module.app.state.budget is not None
    assert main_module.app.state.budget.path == path


def test_startup_handles_unwritable_budget_file(monkeypatch, tmp_path, caplog):
    TestingSessionLocal = _setup_test_session(tmp_path)

    def _session_override():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    import backend.app.main as main_module
    from backend.app.core.settings import settings
    from pathlib import Path

    caplog.set_level(logging.WARNING, logger="backend.app.main")
    monkeypatch.setattr(main_module.logging, "basicConfig", lambda **_k: None)
    monkeypatch.setattr(main_module, "get_session", _session_override)
    monkeypatch.setattr(main_module, "run_etl", lambda *_a, **_k: None)
    monkeypatch.setattr(main_module, "load_seed", lambda: None)
    monkeypatch.setattr(main_module.asyncio, "create_task", lambda coro: coro.close())

    path = tmp_path / "deny" / "budget.json"
    monkeypatch.setattr(settings, "BUDGET_FILE", str(path))

    real_mkdir = Path.mkdir

    def fake_mkdir(self, *args, **kwargs):
        if self == path.parent:
            raise PermissionError("no access")
        return real_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", fake_mkdir)

    asyncio.run(main_module.startup())

    assert getattr(main_module.app.state, "budget", None) is None
    assert any("budget file unavailable" in r.message for r in caplog.records)
