"""Scheduling utilities for cache refresh."""

from __future__ import annotations

import datetime as dt


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


__all__ = ["seconds_until_next_midnight_utc"]
