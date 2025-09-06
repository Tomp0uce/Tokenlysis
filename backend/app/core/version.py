from __future__ import annotations

import os
from pathlib import Path
from subprocess import CalledProcessError, check_output


REPO_ROOT = Path(__file__).resolve().parents[2]


def get_version() -> str:
    """Return the application version.

    The version is primarily derived from the git commit count. When git is not
    available (e.g. in production images where the ``.git`` directory is not
    copied or git isn't installed) the function falls back to the value of the
    ``APP_VERSION`` environment variable. As a last resort it returns ``"0"``.
    """

    try:
        output = check_output(["git", "rev-list", "--count", "HEAD"], cwd=REPO_ROOT)
        return output.decode().strip()
    except (CalledProcessError, FileNotFoundError):
        env_version = os.getenv("APP_VERSION")
        if env_version:
            return env_version
        version_file = REPO_ROOT / "VERSION"
        if version_file.exists():
            return version_file.read_text().strip()
        return "0"


__all__ = ["get_version"]
