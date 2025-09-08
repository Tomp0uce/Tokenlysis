from __future__ import annotations

import logging
from pathlib import Path

from alembic import command, config as alembic_config

from ..core.settings import settings

logger = logging.getLogger(__name__)


def run_migrations() -> None:
    """Run Alembic migrations to the latest version."""
    root = Path(__file__).resolve().parents[3]
    cfg = alembic_config.Config(str(root / "alembic.ini"))
    cfg.attributes["configure_logger"] = False
    cfg.attributes["skip_logging"] = True
    if settings.DATABASE_URL:
        cfg.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
    command.upgrade(cfg, "head")


__all__ = ["run_migrations"]
