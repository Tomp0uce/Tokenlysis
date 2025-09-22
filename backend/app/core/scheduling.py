"""Scheduling utilities for cache refresh."""

from __future__ import annotations

import datetime as dt
import re

_GRANULARITY_PATTERN = re.compile(
    r"^(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>[smhd])$",
    re.IGNORECASE,
)
_UNIT_FACTORS = {
    "s": 1,
    "m": 60,
    "h": 60 * 60,
    "d": 24 * 60 * 60,
}


def seconds_until_next_midnight_utc(now: dt.datetime) -> int:
    """Return number of seconds until next UTC midnight."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=dt.timezone.utc)
    else:
        now = now.astimezone(dt.timezone.utc)
    tomorrow = (now + dt.timedelta(days=1)).date()
    next_midnight = dt.datetime.combine(tomorrow, dt.time(0, 0), tzinfo=dt.timezone.utc)
    delta = next_midnight - now
    return int(delta.total_seconds())


def refresh_granularity_to_seconds(value: str | None, *, default: str = "12h") -> int:
    """Return the refresh interval in seconds based on textual granularity hints."""

    candidates: list[str] = []
    if isinstance(value, str):
        candidate = value.strip()
        if candidate:
            candidates.append(candidate)
    if isinstance(default, str):
        fallback = default.strip()
        if fallback:
            candidates.append(fallback)
    candidates.append("12h")

    for text in candidates:
        lowered = text.lower()
        match = _GRANULARITY_PATTERN.match(lowered)
        if match:
            magnitude = float(match.group("value"))
            unit = match.group("unit").lower()
            seconds = magnitude * _UNIT_FACTORS[unit]
            if seconds > 0:
                return max(int(seconds), 1)
        try:
            number = float(lowered)
        except ValueError:
            continue
        if number > 0:
            return max(int(number), 1)
    return 12 * 60 * 60


def refresh_granularity_to_timedelta(
    value: str | None, *, default: str = "12h"
) -> dt.timedelta:
    """Return the refresh interval as a :class:`datetime.timedelta`."""

    seconds = refresh_granularity_to_seconds(value, default=default)
    return dt.timedelta(seconds=seconds)


__all__ = [
    "refresh_granularity_to_seconds",
    "refresh_granularity_to_timedelta",
    "seconds_until_next_midnight_utc",
]
