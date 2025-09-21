"""Tests for dialect-aware upsert helpers."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects.postgresql.dml import Insert as PostgresInsert

from backend.app.core.settings import settings
from backend.app.etl import run as run_module
from backend.app.etl.run import load_seed
from backend.app.services.dao import PricesRepo


class _FakeSession:
    """Minimal session stub capturing executed statements."""

    def __init__(self, dialect_name: str) -> None:
        dialect = SimpleNamespace(name=dialect_name)
        self.bind = SimpleNamespace(dialect=dialect)
        self.executed: list[tuple[object, object | None]] = []
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def execute(self, stmt, params=None):  # type: ignore[override]
        self.executed.append((stmt, params))
        return None

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        self.closed = True

    def get_bind(self, *args, **kwargs):  # type: ignore[override]
        return self.bind


# T5: ensure seed loading uses PostgreSQL-specific insert when the dialect is postgres

def test_load_seed_supports_postgresql(monkeypatch):
    fake_session = _FakeSession("postgresql")
    monkeypatch.setattr(run_module, "SessionLocal", lambda: fake_session)
    seed_path = Path("backend/app/seed/top20.json").resolve()
    monkeypatch.setattr(settings, "SEED_FILE", str(seed_path))

    load_seed()

    postgres_statements = [
        stmt for stmt, _ in fake_session.executed if isinstance(stmt, PostgresInsert)
    ]
    # prices upsert + three meta upserts should use the PostgreSQL dialect
    assert len(postgres_statements) >= 4
    assert fake_session.committed is True
    assert fake_session.closed is True


# T6: unknown dialects should raise a descriptive error

def test_upsert_latest_rejects_unknown_dialect():
    fake_session = _FakeSession("mysql")
    repo = PricesRepo(fake_session)
    now = dt.datetime.now(dt.timezone.utc)

    with pytest.raises(NotImplementedError) as excinfo:
        repo.upsert_latest(
            [
                {
                    "coin_id": "bitcoin",
                    "vs_currency": "usd",
                    "price": 1.0,
                    "market_cap": 1.0,
                    "fully_diluted_market_cap": 1.0,
                    "volume_24h": 1.0,
                    "rank": 1,
                    "pct_change_24h": 0.0,
                    "pct_change_7d": 0.0,
                    "pct_change_30d": 0.0,
                    "snapshot_at": now,
                }
            ]
        )

    message = str(excinfo.value)
    assert "mysql" in message.lower()
    assert "sqlite" in message.lower() or "postgres" in message.lower()
    assert fake_session.executed == []
