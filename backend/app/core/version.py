from __future__ import annotations

import os
from pathlib import Path
from subprocess import CalledProcessError, check_output

REPO_ROOT = Path(__file__).resolve().parents[2]


def get_version() -> str:
    """Return the application version.

    Prefer the ``APP_VERSION`` environment variable when set to a value other
    than the placeholder ``dev``. When not provided, attempt to read the
    version from a VERSION file generated at build time. As a final fallback,
    return the number of commits in the repository. If everything fails, return
    ``"0"``.
    """

    env_version = os.getenv("APP_VERSION")
    if env_version and env_version != "dev":
        return env_version[:7] if len(env_version) == 40 else env_version

    version_file = REPO_ROOT / "VERSION"
    if version_file.exists():
        version = version_file.read_text().strip()
        return version[:7] if len(version) == 40 else version

    try:
        output = check_output(["git", "rev-list", "--count", "HEAD"], cwd=REPO_ROOT)
        return output.decode().strip()
    except (CalledProcessError, FileNotFoundError):
        return env_version or "0"


__all__ = ["get_version"]
