import asyncio
import logging
import threading

from httpx import ASGITransport, AsyncClient


def test_etl_loop_runs_in_thread_and_endpoints_remain_responsive(monkeypatch):
    asyncio.run(_assert_etl_loop_async(monkeypatch))


async def _assert_etl_loop_async(monkeypatch):
    import backend.app.main as main_module

    # Ensure the application has a budget attribute even if unused in the test.
    main_module.app.state.budget = None

    run_started = threading.Event()
    release_run = threading.Event()

    def blocking_run_etl(*_args, **_kwargs):
        run_started.set()
        release_run.wait(timeout=5)

    monkeypatch.setattr(main_module, "run_etl", blocking_run_etl)
    monkeypatch.setattr(main_module, "refresh_interval_seconds", lambda *_a, **_k: 0)

    stop_event = asyncio.Event()

    loop_task = asyncio.create_task(main_module.etl_loop(stop_event))

    await asyncio.wait_for(asyncio.to_thread(run_started.wait, 5), timeout=5)

    transport = ASGITransport(app=main_module.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await asyncio.wait_for(client.get("/info"), timeout=1)

    await transport.aclose()

    assert response.status_code == 200

    stop_event.set()
    release_run.set()
    await asyncio.wait_for(loop_task, timeout=5)


def test_startup_sync_fear_greed_runs_in_thread_and_tolerates_errors(
    monkeypatch, tmp_path, caplog
):
    asyncio.run(_assert_startup_async(monkeypatch, tmp_path, caplog))


async def _assert_startup_async(monkeypatch, tmp_path, caplog):
    import backend.app.main as main_module
    from backend.app.db import Base
    from backend.app.services.dao import MetaRepo
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(
        f"sqlite:///{tmp_path/'async.db'}", connect_args={"check_same_thread": False}
    )
    TestingSessionLocal = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
    )
    Base.metadata.create_all(bind=engine)

    def _session_override():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    monkeypatch.setattr(main_module, "get_session", _session_override)
    monkeypatch.setattr(main_module, "run_etl", lambda *_a, **_k: 0)
    monkeypatch.setattr(main_module.logging, "basicConfig", lambda **_k: None)

    caplog.set_level(logging.WARNING, logger="backend.app.main")

    recorded_threads: list[str] = []

    def failing_sync(*_args, **_kwargs):
        recorded_threads.append(threading.current_thread().name)
        raise RuntimeError("boom")

    monkeypatch.setattr(main_module, "sync_fear_greed_index", failing_sync)

    await main_module.startup()

    stop_event = getattr(main_module.app.state, "etl_stop_event", None)
    task = getattr(main_module.app.state, "etl_task", None)
    if stop_event is not None:
        stop_event.set()
    if isinstance(task, asyncio.Task):
        await task

    assert recorded_threads, "sync_fear_greed_index should have been called"
    assert recorded_threads[0] != threading.current_thread().name

    session = TestingSessionLocal()
    assert MetaRepo(session).get("bootstrap_done") == "true"
    session.close()

    assert any("startup fear & greed sync skipped" in record.message for record in caplog.records)
