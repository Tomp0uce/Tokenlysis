"""Time-related utility helpers reused across the application."""

from __future__ import annotations

DEFAULT_REFRESH_SECONDS = 12 * 60 * 60


def refresh_interval_seconds(value: str | None, *, default: int = DEFAULT_REFRESH_SECONDS) -> int:
    """Convert ``value`` like ``"12h"`` to seconds, falling back to ``default``.

    The function mirrors :func:`backend.app.main.refresh_interval_seconds` semantics
    so existing behaviour remains unchanged.
    """

    if value is None:
        return default
    text = str(value).strip()
    if not text:
        return default
    try:
        if text.endswith("h"):
            hours = float(text[:-1])
            return int(hours * 60 * 60)
    except Exception:  # pragma: no cover - defensive fallback
        return default
    return default


__all__ = ["refresh_interval_seconds", "DEFAULT_REFRESH_SECONDS"]
