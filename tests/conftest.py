from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
def client(tmp_path) -> Iterator[TestClient]:
    from backend.app.api import deps
    from backend.app.core.config import get_settings
    from backend.app.db import session as db_session
    from backend.app.db.base import Base
    from backend.app.main import create_app

    database_file = tmp_path / "tokenlysis_test.db"
    os.environ["TOKENLYSIS_DATABASE_URL"] = f"sqlite+aiosqlite:///{database_file}"

    get_settings.cache_clear()
    db_session._engine = None  # type: ignore[attr-defined]
    db_session._SessionLocal = None  # type: ignore[attr-defined]

    engine = db_session.get_engine()
    async_session = db_session.get_sessionmaker()

    async def initialize_schema() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(initialize_schema())

    app = create_app()

    async def override_get_db():
        async with async_session() as session:
            yield session

    app.dependency_overrides[deps.get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    async def cleanup_schema() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()

    asyncio.run(cleanup_schema())

    if database_file.exists():
        database_file.unlink()
    db_session._engine = None  # type: ignore[attr-defined]
    db_session._SessionLocal = None  # type: ignore[attr-defined]
    os.environ.pop("TOKENLYSIS_DATABASE_URL", None)
    get_settings.cache_clear()


@pytest.fixture
def authorized_headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-token-with-admin"}


@pytest.fixture
def limited_headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-token-with-user"}
