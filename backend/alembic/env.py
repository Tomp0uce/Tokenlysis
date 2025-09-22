# backend/alembic/env.py
from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path
from typing import Any

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.schema import MetaData


def _load_backend_context() -> tuple[Any, MetaData]:
    """Ensure the repository is on ``sys.path`` and return backend metadata."""

    repo_root = Path(__file__).resolve().parents[2]
    backend_root = repo_root / "backend"
    for candidate in (repo_root, backend_root):
        str_candidate = str(candidate)
        if str_candidate not in sys.path:
            sys.path.insert(0, str_candidate)

    from backend.app.core.settings import settings as loaded_settings
    from backend.app.db import Base

    return loaded_settings, Base.metadata


settings, target_metadata = _load_backend_context()

# Alembic Config
config = context.config

# Source unique de vérité pour l'URL DB
if settings.DATABASE_URL:
    config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# Logging Alembic (si alembic.ini le définit)
if config.config_file_name is not None:  # pragma: no cover - effet de bord Alembic
    fileConfig(config.config_file_name)


def run_migrations_offline() -> None:
    """Exécution offline: utilise l'URL directement."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Exécution online: utilise un engine."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section) or {},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


# Point d'entrée Alembic
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
