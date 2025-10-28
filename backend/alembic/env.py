from __future__ import annotations
import os
from logging.config import fileConfig
from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import Connection

config = context.config
if config and config.config_file_name:
    fileConfig(config.config_file_name)

def _get_db_url() -> str:
    return (
        os.getenv("ALEMBIC_DATABASE_URL")
        or os.getenv("DATABASE_URL")
        or config.get_main_option("sqlalchemy.url")
    )

def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite:")

# target_metadata best-effort (OK à None pour 'upgrade'; seul autogenerate en dépend)
target_metadata = None
try:
    from backend.app.db.base import Base
    target_metadata = Base.metadata
except Exception:
    try:
        from backend.db.base import Base
        target_metadata = Base.metadata
    except Exception:
        target_metadata = None

def run_migrations_offline() -> None:
    url = _get_db_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=_is_sqlite(url),
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section) or {}
    section["sqlalchemy.url"] = _get_db_url()

    connectable = engine_from_config(
        section, prefix="sqlalchemy.", poolclass=pool.NullPool, future=True
    )

    with connectable.connect() as connection:  # type: Connection
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=connection.dialect.name == "sqlite",
        )
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
