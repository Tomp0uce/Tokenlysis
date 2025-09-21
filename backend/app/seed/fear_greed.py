"""Seed helpers for the Fear & Greed index."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

DEFAULT_CLASSIFICATION = "Indéterminé"


def parse_seed_file(path: str | Path) -> list[dict[str, object]]:
    """Parse the historical text export into normalized rows."""

    file_path = Path(path)
    if not file_path.exists():
        return []

    rows: list[dict[str, object]] = []
    with file_path.open(encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line or line.lower().startswith("date"):
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            date_token = parts[0]
            value_token = parts[1]
            label = " ".join(parts[2:]).strip() or DEFAULT_CLASSIFICATION
            try:
                timestamp = dt.datetime.strptime(date_token, "%Y-%m-%d").replace(
                    tzinfo=dt.timezone.utc
                )
            except ValueError:
                continue
            try:
                value = int(float(value_token))
            except ValueError:
                continue
            rows.append(
                {
                    "timestamp": timestamp,
                    "value": value,
                    "classification": label,
                }
            )
    rows.sort(key=lambda item: item["timestamp"])
    return rows


__all__ = ["parse_seed_file", "DEFAULT_CLASSIFICATION"]
