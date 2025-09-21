from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any


class CallBudget:
    """Persisted monthly call counter with quota enforcement."""

    _DEFAULT_CATEGORY = "uncategorized"

    def __init__(self, path: Path, quota: int) -> None:
        self.path = path
        self.quota = quota
        self._data = self._load()

    def _current_month(self) -> str:
        today = dt.date.today()
        return f"{today.year:04d}-{today.month:02d}"

    def _default_payload(self) -> dict[str, Any]:
        return {
            "month": self._current_month(),
            "monthly_call_count": 0,
            "categories": {},
        }

    def _normalise_calls(self, calls: Any) -> int:
        try:
            value = int(calls)
        except (TypeError, ValueError):
            return 0
        return max(value, 0)

    def _normalise_category(self, category: str | None) -> str:
        if category is None:
            return self._DEFAULT_CATEGORY
        name = str(category).strip()
        if not name:
            return self._DEFAULT_CATEGORY
        return name

    def _sanitise_categories(self, payload: dict[str, Any] | None) -> dict[str, int]:
        if not isinstance(payload, dict):
            return {}
        result: dict[str, int] = {}
        for raw_key, raw_value in payload.items():
            key = self._normalise_category(raw_key)
            calls = self._normalise_calls(raw_value)
            if calls <= 0:
                continue
            result[key] = calls
        return result

    def _load(self) -> dict[str, Any]:
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text())
            except Exception:  # pragma: no cover - corrupted file
                raw = None
            if isinstance(raw, dict):
                data = self._default_payload()
                month = raw.get("month")
                data["month"] = month if isinstance(month, str) and month else self._current_month()
                data["monthly_call_count"] = self._normalise_calls(
                    raw.get("monthly_call_count")
                )
                data["categories"] = self._sanitise_categories(raw.get("categories"))
                return data
        return self._default_payload()

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        serialisable = {
            "month": self._data.get("month", self._current_month()),
            "monthly_call_count": self._normalise_calls(
                self._data.get("monthly_call_count")
            ),
            "categories": self._sanitise_categories(self._data.get("categories")),
        }
        self._data = serialisable
        self.path.write_text(json.dumps(serialisable))

    def reset_if_needed(self) -> None:
        current = self._current_month()
        if self._data.get("month") != current:
            self._data = self._default_payload()
            self._data["month"] = current
            self._save()

    def can_spend(self, calls: int) -> bool:
        self.reset_if_needed()
        proposed = self._normalise_calls(calls)
        return self._data["monthly_call_count"] + proposed <= self.quota

    def spend(self, calls: int, *, category: str | None = None) -> None:
        self.reset_if_needed()
        amount = self._normalise_calls(calls)
        if amount <= 0:
            return
        self._data["monthly_call_count"] += amount
        categories = self._data.setdefault("categories", {})
        key = self._normalise_category(category)
        categories[key] = self._normalise_calls(categories.get(key)) + amount
        self._save()

    @property
    def monthly_call_count(self) -> int:
        """Return the current persisted count for this month."""
        self.reset_if_needed()
        return self._data["monthly_call_count"]

    @property
    def category_counts(self) -> dict[str, int]:
        """Return the per-category usage for the current month."""
        self.reset_if_needed()
        categories = self._data.get("categories", {})
        return self._sanitise_categories(categories)
