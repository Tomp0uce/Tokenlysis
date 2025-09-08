from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path("/app")


def get_version() -> str:
    """Return the application version.

    Resolution order:
      1) ``APP_VERSION`` environment variable when set and not ``"dev"``
      2) contents of ``/app/VERSION`` written at build time
      3) fallback to ``"dev"``
    """

    env_version = os.getenv("APP_VERSION")
    if env_version and env_version != "dev":
        return env_version

    version_file = REPO_ROOT / "VERSION"
    if version_file.exists():
        content = version_file.read_text().strip()
        if content:
            return content

    return "dev"


__all__ = ["get_version"]
