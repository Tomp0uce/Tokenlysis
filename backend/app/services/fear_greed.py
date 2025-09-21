"""Synchronise the Crypto Fear & Greed index."""

from __future__ import annotations

import datetime as dt
import logging
from typing import Iterable

import requests

from ..db import SessionLocal
from .coinmarketcap import CoinMarketCapClient, build_default_client
from .dao import FearGreedRepo, MetaRepo

DEFAULT_CLASSIFICATION = "Indéterminé"

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
    value = _normalize_value(entry.get("value"))
    if value is None:
        return None
    classification_raw = (
        entry.get("value_classification")
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


def sync_fear_greed_index(
    *,
    session=None,
    client: CoinMarketCapClient | None = None,
    now: dt.datetime | None = None,
) -> int:
    """Seed the database and fetch the latest values from CoinMarketCap."""

    managed_session = False
    if session is None:
        session = SessionLocal()
        managed_session = True
    repo = FearGreedRepo(session)
    meta_repo = MetaRepo(session)
    client = client or build_default_client()
    timestamp_now = now or dt.datetime.now(dt.timezone.utc)
    processed = 0
    try:
        try:
            history = client.get_fear_greed_history()
            processed += _ingest_history(repo, history, timestamp_now)
        except requests.RequestException as exc:
            logger.warning("fear & greed history fetch failed: %s", exc)
        try:
            latest = client.get_fear_greed_latest()
            if latest:
                processed += _ingest_history(repo, [latest], timestamp_now)
        except requests.RequestException as exc:
            logger.warning("fear & greed latest fetch failed: %s", exc)
        if processed:
            meta_repo.set("fear_greed_last_refresh", timestamp_now.isoformat())
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        if managed_session:
            session.close()
    return processed

__all__ = ["sync_fear_greed_index", "DEFAULT_CLASSIFICATION"]
