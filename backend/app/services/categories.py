"""Category helpers."""

from __future__ import annotations

import re


def slugify(name: str) -> str:
    """Normalize category name to a slug id."""
    lowered = name.lower()
    no_paren = re.sub(r"\([^)]*\)", "", lowered)
    cleaned = re.sub(r"[^a-z0-9]+", "-", no_paren)
    return cleaned.strip("-")


__all__ = ["slugify"]
