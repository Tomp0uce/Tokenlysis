from __future__ import annotations

import datetime as dt
import json
from pathlib import Path


class CallBudget:
    """Persisted monthly call counter with quota enforcement."""

    def __init__(self, path: Path, quota: int) -> None:
        self.path = path
        self.quota = quota
        self._data = self._load()

    def _current_month(self) -> str:
        today = dt.date.today()
        return f"{today.year:04d}-{today.month:02d}"

    def _load(self) -> dict:
        if self.path.exists():
            try:
                return json.loads(self.path.read_text())
            except Exception:  # pragma: no cover - corrupted file
                pass
        return {"month": self._current_month(), "monthly_call_count": 0}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._data))

    def reset_if_needed(self) -> None:
        current = self._current_month()
        if self._data.get("month") != current:
            self._data = {"month": current, "monthly_call_count": 0}
            self._save()

    def can_spend(self, calls: int) -> bool:
        self.reset_if_needed()
        return self._data["monthly_call_count"] + calls <= self.quota

    def spend(self, calls: int) -> None:
        self.reset_if_needed()
        self._data["monthly_call_count"] += calls
        self._save()

    @property
    def monthly_call_count(self) -> int:
        """Return the current persisted count for this month."""
        self.reset_if_needed()
        return self._data["monthly_call_count"]
