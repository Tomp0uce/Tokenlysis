import asyncio
import contextlib
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


def _patch_historical_import(monkeypatch, main_module, calls=None):
    def _fake_import(session, *_args, **_kwargs):
        if calls is not None:
            calls.setdefault("count", 0)
            calls["count"] += 1

    monkeypatch.setattr(
        main_module, "import_historical_data", _fake_import, raising=False
    )


def test_startup_runs_etl_when_not_bootstrapped(monkeypatch, tmp_path):
    TestingSessionLocal = _setup_test_session(tmp_path)

    def _session_override():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    import backend.app.main as main_module

    monkeypatch.setattr(main_module.settings, "log_level", "DEBUG")
    monkeypatch.setattr(main_module.logging, "basicConfig", lambda **_k: None)
    monkeypatch.setattr(main_module, "get_session", _session_override)
    monkeypatch.setattr(main_module.asyncio, "create_task", lambda coro: coro.close())
    called = {"etl": 0, "seed": 0}

    async def fake_run_etl_async(*_a, **_k):
        called["etl"] += 1
        return 0

    async def fake_sync_async() -> int:
        return 0

    def fake_load_seed():
        called["seed"] += 1

    monkeypatch.setattr(main_module, "run_etl_async", fake_run_etl_async)
    monkeypatch.setattr(main_module, "sync_fear_greed_async", fake_sync_async)
    monkeypatch.setattr(main_module, "load_seed", fake_load_seed)
    _patch_historical_import(monkeypatch, main_module)

    main_module.app.state.startup_path = None
    asyncio.run(main_module.startup())

    assert called["etl"] == 1
    assert called["seed"] == 0
    assert getattr(main_module.app.state, "startup_path", None) == "ETL"


def test_startup_runs_historical_import_after_etl(monkeypatch, tmp_path):
    TestingSessionLocal = _setup_test_session(tmp_path)

    def _session_override():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    import backend.app.main as main_module

    monkeypatch.setattr(main_module.settings, "log_level", "DEBUG")
    monkeypatch.setattr(main_module.logging, "basicConfig", lambda **_k: None)
    monkeypatch.setattr(main_module, "get_session", _session_override)
    monkeypatch.setattr(main_module.asyncio, "create_task", lambda coro: coro.close())

    order = {"etl_done": False, "import_calls": 0}

    async def fake_run_etl_async(*_a, **_k):
        order["etl_done"] = True
        return 0

    async def fake_sync_async() -> int:
        return 0

    def fake_load_seed() -> None:  # pragma: no cover - should not run
        raise AssertionError("load_seed should not run when ETL succeeds")

    def fake_import(session, *_a, **_k):
        assert order["etl_done"], "historical import ran before ETL finished"
        order["import_calls"] += 1

    monkeypatch.setattr(main_module, "run_etl_async", fake_run_etl_async)
    monkeypatch.setattr(main_module, "sync_fear_greed_async", fake_sync_async)
    monkeypatch.setattr(main_module, "load_seed", fake_load_seed)
    monkeypatch.setattr(main_module, "import_historical_data", fake_import, raising=False)

    main_module.app.state.startup_path = None
    asyncio.run(main_module.startup())

    assert order["import_calls"] == 1


def test_startup_retries_historical_import_after_failure(monkeypatch, tmp_path):
    TestingSessionLocal = _setup_test_session(tmp_path)

    def _session_override():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    import backend.app.main as main_module

    monkeypatch.setattr(main_module.settings, "log_level", "DEBUG")
    monkeypatch.setattr(main_module.logging, "basicConfig", lambda **_k: None)
    monkeypatch.setattr(main_module, "get_session", _session_override)
    monkeypatch.setattr(main_module.asyncio, "create_task", lambda coro: coro.close())

    calls: dict[str, int] = {"etl": 0, "import": 0}

    async def fake_run_etl_async(*_a, **_k):
        calls["etl"] += 1
        session = TestingSessionLocal()
        try:
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
        finally:
            session.close()

    async def fake_sync_async() -> int:
        return 0

    def fake_load_seed() -> None:  # pragma: no cover - should not run
        raise AssertionError("seed should not run when ETL succeeds")

    def fake_import(session, *_a, **_k):
        calls["import"] += 1
        if calls["import"] == 1:
            raise RuntimeError("transient historical import failure")

    monkeypatch.setattr(main_module, "run_etl_async", fake_run_etl_async)
    monkeypatch.setattr(main_module, "sync_fear_greed_async", fake_sync_async)
    monkeypatch.setattr(main_module, "load_seed", fake_load_seed)
    monkeypatch.setattr(main_module, "import_historical_data", fake_import, raising=False)

    main_module.app.state.startup_path = None
    asyncio.run(main_module.startup())

    session = TestingSessionLocal()
    try:
        assert MetaRepo(session).get("historical_import_done") == "false"
    finally:
        session.close()

    main_module.app.state.startup_path = None
    asyncio.run(main_module.startup())

    assert calls == {"etl": 1, "import": 2}

    session = TestingSessionLocal()
    try:
        assert MetaRepo(session).get("historical_import_done") == "true"
    finally:
        session.close()


def test_startup_skips_when_bootstrapped_and_has_data(monkeypatch, tmp_path):
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

    monkeypatch.setattr(main_module.settings, "log_level", "DEBUG")
    monkeypatch.setattr(main_module.logging, "basicConfig", lambda **_k: None)
    monkeypatch.setattr(main_module, "get_session", _session_override)
    monkeypatch.setattr(main_module.asyncio, "create_task", lambda coro: coro.close())
    called = {"etl": 0, "seed": 0}

    async def fake_run_etl_async(*_a, **_k):
        called["etl"] += 1
        return 0

    async def fake_sync_async() -> int:
        return 0

    def fake_load_seed():
        called["seed"] += 1

    monkeypatch.setattr(main_module, "run_etl_async", fake_run_etl_async)
    monkeypatch.setattr(main_module, "sync_fear_greed_async", fake_sync_async)
    monkeypatch.setattr(main_module, "load_seed", fake_load_seed)
    _patch_historical_import(monkeypatch, main_module)

    main_module.app.state.startup_path = None
    asyncio.run(main_module.startup())

    assert called["etl"] == 0
    assert called["seed"] == 0
    assert getattr(main_module.app.state, "startup_path", None) == "skip"


def test_startup_handles_missing_seed_when_etl_fails(monkeypatch, tmp_path):
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

    monkeypatch.setattr(main_module.settings, "log_level", "DEBUG")
    monkeypatch.setattr(main_module.logging, "basicConfig", lambda **_k: None)
    monkeypatch.setattr(main_module, "get_session", _session_override)
    monkeypatch.setattr(main_module.asyncio, "create_task", lambda coro: coro.close())

    seed_calls = {"count": 0}

    async def fake_run_etl_async(*_a, **_k):
        raise main_module.DataUnavailable

    async def fake_sync_async() -> int:
        return 0

    def fake_load_seed():
        seed_calls["count"] += 1
        run_module.load_seed()

    monkeypatch.setattr(main_module, "run_etl_async", fake_run_etl_async)
    monkeypatch.setattr(main_module, "sync_fear_greed_async", fake_sync_async)
    monkeypatch.setattr(main_module, "load_seed", fake_load_seed)
    monkeypatch.setattr(settings, "SEED_FILE", str(tmp_path / "missing.json"))
    _patch_historical_import(monkeypatch, main_module)

    main_module.app.state.startup_path = None
    asyncio.run(main_module.startup())

    assert seed_calls["count"] == 1
    session = TestingSessionLocal()
    assert MetaRepo(session).get("bootstrap_done") == "true"
    session.close()
    assert getattr(main_module.app.state, "startup_path", None) == "seed"


def test_startup_runs_historical_import_after_seed(monkeypatch, tmp_path):
    TestingSessionLocal = _setup_test_session(tmp_path)

    def _session_override():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    import backend.app.main as main_module
    from backend.app.core.settings import settings

    monkeypatch.setattr(main_module.settings, "log_level", "DEBUG")
    monkeypatch.setattr(main_module.logging, "basicConfig", lambda **_k: None)
    monkeypatch.setattr(main_module, "get_session", _session_override)
    monkeypatch.setattr(main_module.asyncio, "create_task", lambda coro: coro.close())

    order = {"seed_loaded": False, "import_calls": 0}

    async def fake_run_etl_async(*_a, **_k):
        raise main_module.DataUnavailable

    async def fake_sync_async() -> int:
        return 0

    def fake_load_seed():
        order["seed_loaded"] = True

    def fake_import(session, *_a, **_k):
        assert order["seed_loaded"], "historical import ran before seed load"
        order["import_calls"] += 1

    monkeypatch.setattr(main_module, "run_etl_async", fake_run_etl_async)
    monkeypatch.setattr(main_module, "sync_fear_greed_async", fake_sync_async)
    monkeypatch.setattr(main_module, "load_seed", fake_load_seed)
    monkeypatch.setattr(main_module, "import_historical_data", fake_import, raising=False)
    monkeypatch.setattr(settings, "use_seed_on_failure", True)

    main_module.app.state.startup_path = None
    asyncio.run(main_module.startup())

    assert order["import_calls"] == 1


def test_startup_bootstrapped_empty_table_runs_etl(monkeypatch, tmp_path):
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

    monkeypatch.setattr(main_module.settings, "log_level", "DEBUG")
    monkeypatch.setattr(main_module.logging, "basicConfig", lambda **_k: None)
    monkeypatch.setattr(main_module, "get_session", _session_override)
    monkeypatch.setattr(main_module.asyncio, "create_task", lambda coro: coro.close())

    called = {"etl": 0, "seed": 0}

    async def fake_run_etl_async(*_a, **_k):
        called["etl"] += 1
        return 0

    async def fake_sync_async() -> int:
        return 0

    def fake_load_seed():
        called["seed"] += 1

    monkeypatch.setattr(main_module, "run_etl_async", fake_run_etl_async)
    monkeypatch.setattr(main_module, "sync_fear_greed_async", fake_sync_async)
    monkeypatch.setattr(main_module, "load_seed", fake_load_seed)
    _patch_historical_import(monkeypatch, main_module)

    main_module.app.state.startup_path = None
    asyncio.run(main_module.startup())

    assert called["etl"] == 1
    assert called["seed"] == 0
    assert getattr(main_module.app.state, "startup_path", None) == "ETL"


def test_startup_bootstrapped_empty_table_etl_fails_uses_seed(
    monkeypatch, tmp_path
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

    monkeypatch.setattr(main_module.settings, "log_level", "DEBUG")
    monkeypatch.setattr(main_module.logging, "basicConfig", lambda **_k: None)
    monkeypatch.setattr(main_module, "get_session", _session_override)
    monkeypatch.setattr(main_module.asyncio, "create_task", lambda coro: coro.close())

    called = {"etl": 0, "seed": 0}

    async def fake_run_etl_async(*_a, **_k):
        called["etl"] += 1
        raise main_module.DataUnavailable

    async def fake_sync_async() -> int:
        return 0

    def fake_load_seed():
        called["seed"] += 1

    monkeypatch.setattr(main_module, "run_etl_async", fake_run_etl_async)
    monkeypatch.setattr(main_module, "sync_fear_greed_async", fake_sync_async)
    monkeypatch.setattr(main_module, "load_seed", fake_load_seed)
    _patch_historical_import(monkeypatch, main_module)

    main_module.app.state.startup_path = None
    asyncio.run(main_module.startup())

    assert called["etl"] == 1
    assert called["seed"] == 1
    assert getattr(main_module.app.state, "startup_path", None) == "seed"


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

    original_create_task = asyncio.create_task

    async def fake_run_etl_async(*_a, **_k):
        run_calls.append(1)
        return 0

    async def fake_sync_async() -> int:
        return 0

    async def fake_wait_for(awaitable, timeout):
        sleep_args.append(timeout)
        task = original_create_task(awaitable)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        raise RuntimeError

    tasks = []

    def fake_create_task(coro):
        tasks.append(coro)
        return None

    monkeypatch.setattr(main_module, "run_etl_async", fake_run_etl_async)
    monkeypatch.setattr(main_module, "sync_fear_greed_async", fake_sync_async)
    monkeypatch.setattr(main_module, "load_seed", lambda: None)
    monkeypatch.setattr(main_module.asyncio, "wait_for", fake_wait_for)
    monkeypatch.setattr(main_module.asyncio, "create_task", fake_create_task)
    _patch_historical_import(monkeypatch, main_module)

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
    original_create_task = asyncio.create_task

    async def fake_run_etl_async(*_a, **_k):
        return 0

    async def fake_wait_for(awaitable, timeout):
        sleep_calls.append(timeout)
        task = original_create_task(awaitable)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        if len(sleep_calls) == 1:
            settings.REFRESH_GRANULARITY = "1h"
            raise asyncio.TimeoutError
        raise RuntimeError

    monkeypatch.setattr(main_module, "run_etl_async", fake_run_etl_async)
    monkeypatch.setattr(main_module.asyncio, "wait_for", fake_wait_for)

    orig = settings.REFRESH_GRANULARITY
    settings.REFRESH_GRANULARITY = "2h"
    stop_event = asyncio.Event()
    with pytest.raises(RuntimeError):
        asyncio.run(main_module.etl_loop(stop_event))
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

    async def fake_run_etl_async(*_a, **_k):
        return 0

    async def fake_sync_async() -> int:
        return 0

    monkeypatch.setattr(main_module, "run_etl_async", fake_run_etl_async)
    monkeypatch.setattr(main_module, "sync_fear_greed_async", fake_sync_async)
    monkeypatch.setattr(main_module, "load_seed", lambda: None)
    monkeypatch.setattr(main_module.asyncio, "create_task", lambda coro: coro.close())
    _patch_historical_import(monkeypatch, main_module)

    path = tmp_path / "meta" / "budget.json"
    monkeypatch.setattr(settings, "BUDGET_FILE", str(path))

    asyncio.run(main_module.startup())

    assert path.parent.exists()
    assert main_module.app.state.budget is not None
    assert main_module.app.state.budget.path == path
    assert main_module.app.state.cmc_budget is None


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

    async def fake_run_etl_async(*_a, **_k):
        return 0

    async def fake_sync_async() -> int:
        return 0

    monkeypatch.setattr(main_module, "run_etl_async", fake_run_etl_async)
    monkeypatch.setattr(main_module, "sync_fear_greed_async", fake_sync_async)
    monkeypatch.setattr(main_module, "load_seed", lambda: None)
    monkeypatch.setattr(main_module.asyncio, "create_task", lambda coro: coro.close())
    _patch_historical_import(monkeypatch, main_module)

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


def test_startup_invokes_historical_import_once(monkeypatch, tmp_path):
    TestingSessionLocal = _setup_test_session(tmp_path)

    def _session_override():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    import backend.app.main as main_module

    monkeypatch.setattr(main_module.settings, "log_level", "DEBUG")
    monkeypatch.setattr(main_module.logging, "basicConfig", lambda **_k: None)
    monkeypatch.setattr(main_module, "get_session", _session_override)
    monkeypatch.setattr(main_module.asyncio, "create_task", lambda coro: coro.close())

    calls = {"count": 0}
    _patch_historical_import(monkeypatch, main_module, calls)

    async def fake_run_etl_async(*_a, **_k):
        return 0

    async def fake_sync_async() -> int:
        return 0

    monkeypatch.setattr(main_module, "run_etl_async", fake_run_etl_async)
    monkeypatch.setattr(main_module, "sync_fear_greed_async", fake_sync_async)
    monkeypatch.setattr(main_module, "load_seed", lambda: None)

    asyncio.run(main_module.startup())

    assert calls["count"] == 1
