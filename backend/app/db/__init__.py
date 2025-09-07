"""Database utilities and session management."""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session

from ..core.settings import settings


class Base(DeclarativeBase):
    """Base class for all ORM models."""


def _build_engine() -> Engine:
    url = settings.DATABASE_URL or "sqlite:///./tokenlysis.db"
    if url.startswith("sqlite"):
        # Ensure parent directory exists and enable WAL.
        db_path = url.split("///")[-1]
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(
            url, connect_args={"check_same_thread": False}, pool_pre_ping=True
        )
        with engine.connect() as conn:  # pragma: no cover - side effect
            conn.execute(text("PRAGMA journal_mode=WAL"))
        return engine
    return create_engine(url, pool_pre_ping=True)


engine: Engine = _build_engine()

SessionLocal = sessionmaker(
    bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
)


def get_session() -> Iterator[Session]:
    """Yield a database session for FastAPI dependencies."""

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


__all__ = ["Base", "engine", "SessionLocal", "get_session"]
