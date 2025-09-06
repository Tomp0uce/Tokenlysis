from __future__ import annotations

from pathlib import Path
from subprocess import CalledProcessError, check_output


REPO_ROOT = Path(__file__).resolve().parents[2]


def get_version() -> str:
    """Return commit count as version string."""
    try:
        output = check_output(["git", "rev-list", "--count", "HEAD"], cwd=REPO_ROOT)
        return output.decode().strip()
    except (CalledProcessError, FileNotFoundError):
        return "0"


__all__ = ["get_version"]
