"""Synchronise the Crypto Fear & Greed index."""

from __future__ import annotations

import datetime as dt
import logging
from typing import Iterable

import requests

from ..clients.cmc_fng import (
    CoinMarketCapFearGreedClient,
    build_default_client,
)
from ..core.scheduling import refresh_granularity_to_timedelta
from ..core.settings import settings
from ..db import Base, SessionLocal
from .budget import CallBudget
from .dao import FearGreedRepo, MetaRepo

DEFAULT_CLASSIFICATION = "Indéterminé"
_MIN_HISTORY_SPAN = dt.timedelta(days=365 * 2)

logger = logging.getLogger(__name__)


def _ensure_timezone(ts: dt.datetime) -> dt.datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=dt.timezone.utc)
    return ts.astimezone(dt.timezone.utc)


def _parse_timestamp(raw: object) -> dt.datetime | None:
    if isinstance(raw, dt.datetime):
        return _ensure_timezone(raw)
    if isinstance(raw, str):
        candidate = raw.strip()
        if not candidate:
            return None
        if candidate.endswith("Z"):
            candidate = candidate[:-1] + "+00:00"
        try:
            return _ensure_timezone(dt.datetime.fromisoformat(candidate))
        except ValueError:
            try:
                return dt.datetime.strptime(candidate, "%Y-%m-%d").replace(
                    tzinfo=dt.timezone.utc
                )
            except ValueError:
                return None
    return None


def _normalize_value(raw: object) -> int | None:
    try:
        value = int(round(float(raw)))
    except (TypeError, ValueError):
        return None
    return max(0, min(100, value))


def _normalize_entry(entry: dict, ingested_at: dt.datetime) -> dict | None:
    timestamp = _parse_timestamp(entry.get("timestamp") or entry.get("time"))
    if timestamp is None:
        return None
    score_source = entry.get("score") if "score" in entry else entry.get("value")
    value = _normalize_value(score_source)
    if value is None:
        return None
    classification_raw = (
        entry.get("label")
        or entry.get("value_classification")
        or entry.get("classification")
        or DEFAULT_CLASSIFICATION
    )
    classification = str(classification_raw).strip() or DEFAULT_CLASSIFICATION
    return {
        "timestamp": timestamp,
        "value": value,
        "classification": classification,
        "ingested_at": ingested_at,
    }


def _ingest_history(
    repo: FearGreedRepo,
    entries: Iterable[dict],
    now: dt.datetime,
) -> int:
    buffered = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        normalized = _normalize_entry(entry, now)
        if normalized is not None:
            buffered.append(normalized)
    if not buffered:
        return 0
    repo.upsert_many(buffered)
    return len(buffered)


def _budget_allows(budget: CallBudget | None, category: str) -> bool:
    if budget is None:
        return True
    if budget.can_spend(1):
        return True
    logger.warning(
        "fear & greed %s fetch skipped: CMC quota exceeded",
        category,
        extra={
            "category": category,
            "monthly_call_count": budget.monthly_call_count,
            "quota": settings.CMC_MONTHLY_QUOTA,
        },
    )
    return False


def sync_fear_greed_index(
    *,
    session=None,
    client: CoinMarketCapFearGreedClient | None = None,
    now: dt.datetime | None = None,
    budget: CallBudget | None = None,
) -> int:
    """Seed the database and fetch the latest values from CoinMarketCap."""

    managed_session = False
    if session is None:
        session = SessionLocal()
        managed_session = True
    try:
        repo = FearGreedRepo(session)
        meta_repo = MetaRepo(session)
        try:
            Base.metadata.create_all(bind=session.get_bind(), checkfirst=True)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("fear & greed table ensure failed: %s", exc)
        timestamp_now = now or dt.datetime.now(dt.timezone.utc)
        guard_interval = refresh_granularity_to_timedelta(settings.REFRESH_GRANULARITY)
        interval_seconds = max(int(guard_interval.total_seconds()), 1)
        last_refresh = _parse_timestamp(meta_repo.get("fear_greed_last_refresh"))
        existing_points = repo.count()
        if (
            existing_points > 0
            and last_refresh is not None
            and (timestamp_now - last_refresh) < guard_interval
        ):
            logger.info(
                "fear & greed sync skipped: refresh cadence not reached",
                extra={
                    "last_refresh_at": last_refresh.isoformat(),
                    "interval_seconds": interval_seconds,
                },
            )
            return 0

        earliest_ts, latest_ts = repo.get_timespan()
        history_span: dt.timedelta | None = None
        if earliest_ts is not None and latest_ts is not None:
            earliest_norm = _ensure_timezone(earliest_ts)
            latest_norm = _ensure_timezone(latest_ts)
            history_span = latest_norm - earliest_norm

        latest_row = repo.get_latest()
        latest_timestamp = (
            _ensure_timezone(latest_row.timestamp) if latest_row else None
        )
        has_today_value = (
            latest_timestamp is not None
            and latest_timestamp.date() == timestamp_now.date()
        )
        has_multi_year_history = (
            history_span is not None and history_span >= _MIN_HISTORY_SPAN
        )
        should_fetch_history = not has_multi_year_history
        should_fetch_latest = not has_today_value

        if not should_fetch_history and not should_fetch_latest:
            logger.info(
                "fear & greed sync skipped: multi-year cache is up-to-date",
                extra={
                    "history_span_days": (
                        int(history_span.days) if history_span is not None else None
                    ),
                    "latest_timestamp": (
                        latest_timestamp.isoformat() if latest_timestamp else None
                    ),
                },
            )
            return 0

        client = client or build_default_client()
        processed = 0
        try:
            if budget is not None:
                budget.reset_if_needed()

            if should_fetch_history and _budget_allows(budget, "cmc_history"):
                history_call_charged = False
                try:
                    history = client.get_historical()
                except requests.RequestException as exc:
                    logger.warning("fear & greed history fetch failed: %s", exc)
                    if budget is not None:
                        budget.spend(1, category="cmc_history")
                        history_call_charged = True
                else:
                    ingested = _ingest_history(repo, history, timestamp_now)
                    processed += ingested
                    if ingested:
                        latest_row = repo.get_latest()
                        latest_timestamp = (
                            _ensure_timezone(latest_row.timestamp)
                            if latest_row
                            else None
                        )
                        has_today_value = (
                            latest_timestamp is not None
                            and latest_timestamp.date() == timestamp_now.date()
                        )
                finally:
                    if budget is not None and not history_call_charged:
                        budget.spend(1, category="cmc_history")

            if should_fetch_latest and not has_today_value and _budget_allows(
                budget, "cmc_latest"
            ):
                try:
                    latest = client.get_latest()
                except requests.RequestException as exc:
                    logger.warning("fear & greed latest fetch failed: %s", exc)
                else:
                    if latest:
                        ingested_latest = _ingest_history(
                            repo, [latest], timestamp_now
                        )
                        processed += ingested_latest
                        if ingested_latest:
                            has_today_value = True
                finally:
                    if budget is not None:
                        budget.spend(1, category="cmc_latest")

            if processed:
                meta_repo.set("fear_greed_last_refresh", timestamp_now.isoformat())
            session.commit()
        except Exception:
            session.rollback()
            raise
        return processed
    finally:
        if managed_session:
            session.close()


__all__ = ["sync_fear_greed_index", "DEFAULT_CLASSIFICATION"]
