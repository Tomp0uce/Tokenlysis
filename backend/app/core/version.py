from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

_VERSION_CACHE: str | None = None


def _cache(value: str) -> str:
    global _VERSION_CACHE
    _VERSION_CACHE = value
    return value


def _resolve_version_file() -> Path:
    version_file_env = os.getenv("VERSION_FILE")
    if version_file_env:
        return Path(version_file_env)
    repo_parent_version = REPO_ROOT.parent / "VERSION"
    if repo_parent_version.exists():
        return repo_parent_version
    return REPO_ROOT / "VERSION"


def get_version(*, force_refresh: bool = False) -> str:
    """Return the application version.

    Resolution order:
      1) ``APP_VERSION`` environment variable when set and not ``"dev"``
      2) contents of ``VERSION`` file located at the project root (``/app/VERSION``
         in containers) or next to the backend package when present (override with
         ``VERSION_FILE`` environment variable)
      3) fallback to ``"dev"``
    """

    if _VERSION_CACHE is not None and not force_refresh:
        return _VERSION_CACHE

    env_version = os.getenv("APP_VERSION")
    if env_version and env_version != "dev":
        return _cache(env_version)

    version_file = _resolve_version_file()
    try:
        content = version_file.read_text(encoding="utf-8").strip()
    except OSError:
        content = ""

    if content:
        return _cache(content)

    return _cache("dev")


__all__ = ["get_version"]
