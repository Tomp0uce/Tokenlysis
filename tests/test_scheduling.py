from datetime import datetime, timezone

from backend.app.core.scheduling import seconds_until_next_midnight_utc


def test_seconds_until_next_midnight():
    now = datetime(2024, 1, 1, 23, 59, 30, tzinfo=timezone.utc)
    assert seconds_until_next_midnight_utc(now) == 30


def test_seconds_until_next_midnight_midday():
    now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    assert seconds_until_next_midnight_utc(now) == 12 * 60 * 60
