# backend/alembic/env.py
from __future__ import annotations

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# --- Assure que /app est dans le PYTHONPATH pour importer 'backend' ---
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Imports projet
from backend.app.core.settings import settings
from backend.app.db import Base

# Alembic Config
config = context.config

# Source unique de vérité pour l'URL DB
if settings.DATABASE_URL:
    config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# Logging Alembic (si alembic.ini le définit)
if config.config_file_name is not None:  # pragma: no cover - effet de bord Alembic
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


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
