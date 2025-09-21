"""Database repositories."""

from __future__ import annotations

import datetime as dt
from typing import Iterable, Sequence
import logging
import json

from sqlalchemy import select, insert, func
from sqlalchemy.exc import OperationalError
from sqlalchemy.dialects.sqlite import insert as sqlite_upsert
from sqlalchemy.dialects.postgresql import insert as postgres_upsert
from sqlalchemy.orm import Session
from sqlalchemy.sql import Insert

from ..models import Coin, LatestPrice, Meta, Price, FearGreed

logger = logging.getLogger(__name__)


def _detect_dialect(session: Session) -> str:
    """Return the current session dialect name in lowercase."""

    bind = getattr(session, "bind", None)
    if bind is None:
        try:
            bind = session.get_bind()
        except Exception as exc:  # pragma: no cover - defensive
            raise RuntimeError("session is not bound to an engine") from exc
    dialect = getattr(bind, "dialect", None)
    if dialect is None or not getattr(dialect, "name", None):
        raise RuntimeError("session bind has no dialect information")
    return str(dialect.name).lower()


def _upsert(session: Session, model, rows: Sequence[dict]) -> Insert:  # type: ignore[type-arg]
    """Build an insert statement suited for the session dialect."""

    dialect_name = _detect_dialect(session)
    if dialect_name == "sqlite":
        return sqlite_upsert(model).values(list(rows))
    if dialect_name in {"postgresql", "postgres"}:
        return postgres_upsert(model).values(list(rows))
    raise NotImplementedError(
        f"Unsupported database dialect '{dialect_name}'. "
        "Upsert statements are implemented only for SQLite and PostgreSQL."
    )


class PricesRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_top(self, vs: str, limit: int) -> list[LatestPrice]:
        stmt = (
            select(LatestPrice)
            .where(LatestPrice.vs_currency == vs)
            .order_by(LatestPrice.rank)
            .limit(limit)
        )
        return list(self.session.scalars(stmt))

    def get_price(self, coin_id: str, vs: str) -> LatestPrice | None:
        stmt = select(LatestPrice).where(
            LatestPrice.coin_id == coin_id, LatestPrice.vs_currency == vs
        )
        return self.session.scalar(stmt)

    def get_history(
        self, coin_id: str, vs: str, since: dt.datetime | None = None
    ) -> list[Price]:
        stmt = select(Price).where(Price.coin_id == coin_id, Price.vs_currency == vs)
        if since is not None:
            stmt = stmt.where(Price.snapshot_at >= since)
        stmt = stmt.order_by(Price.snapshot_at)
        return list(self.session.scalars(stmt))

    def upsert_latest(self, rows: Iterable[dict]) -> None:
        buffered = list(rows)
        if not buffered:
            return
        stmt = _upsert(self.session, LatestPrice, buffered)
        stmt = stmt.on_conflict_do_update(
            index_elements=[LatestPrice.coin_id, LatestPrice.vs_currency],
            set_={
                "price": stmt.excluded.price,
                "market_cap": stmt.excluded.market_cap,
                "fully_diluted_market_cap": stmt.excluded.fully_diluted_market_cap,
                "volume_24h": stmt.excluded.volume_24h,
                "rank": stmt.excluded.rank,
                "pct_change_24h": stmt.excluded.pct_change_24h,
                "pct_change_7d": stmt.excluded.pct_change_7d,
                "pct_change_30d": stmt.excluded.pct_change_30d,
                "snapshot_at": stmt.excluded.snapshot_at,
            },
        )
        self.session.execute(stmt)

    def insert_snapshot(self, rows: Iterable[dict]) -> None:
        if not rows:
            return
        self.session.execute(insert(Price), list(rows))


class CoinsRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    @staticmethod
    def _empty_details() -> dict[str, object]:
        return {
            "category_names": [],
            "category_ids": [],
            "name": "",
            "symbol": "",
            "logo_url": None,
            "social_links": {},
        }

    @staticmethod
    def _build_details(row: Coin | None) -> dict[str, object]:
        details = CoinsRepo._empty_details()
        if row is None:
            return details
        details["category_names"] = (
            json.loads(row.category_names) if row.category_names else []
        )
        details["category_ids"] = json.loads(row.category_ids) if row.category_ids else []
        details["name"] = row.name or ""
        details["symbol"] = row.symbol or ""
        details["logo_url"] = row.logo_url
        try:
            details["social_links"] = (
                json.loads(row.social_links) if row.social_links else {}
            )
        except json.JSONDecodeError:
            details["social_links"] = {}
        return details

    def upsert(self, rows: Iterable[dict]) -> None:
        buffered = list(rows)
        if not buffered:
            return
        stmt = _upsert(self.session, Coin, buffered)
        stmt = stmt.on_conflict_do_update(
            index_elements=[Coin.id],
            set_={
                "symbol": stmt.excluded.symbol,
                "name": stmt.excluded.name,
                "logo_url": stmt.excluded.logo_url,
                "category_names": stmt.excluded.category_names,
                "category_ids": stmt.excluded.category_ids,
                "social_links": stmt.excluded.social_links,
                "updated_at": stmt.excluded.updated_at,
            },
        )
        self.session.execute(stmt)

    def get_categories(self, coin_id: str) -> tuple[list[str], list[str]]:
        details = self.get_details(coin_id)
        return list(details["category_names"]), list(details["category_ids"])

    def get_categories_bulk(
        self, coin_ids: list[str]
    ) -> dict[str, tuple[list[str], list[str]]]:
        details_map = self.get_details_bulk(coin_ids)
        return {
            coin_id: (
                list(info["category_names"]),
                list(info["category_ids"]),
            )
            for coin_id, info in details_map.items()
        }

    def get_details_bulk(self, coin_ids: list[str]) -> dict[str, dict[str, object]]:
        if not coin_ids:
            return {}
        stmt = select(Coin).where(Coin.id.in_(coin_ids))
        try:
            result = self.session.execute(stmt)
            rows = list(result.scalars())
        except OperationalError as exc:
            logger.warning("schema out-of-date: %s", exc)
            return {cid: self._empty_details() for cid in coin_ids}
        details_map: dict[str, dict[str, object]] = {}
        for row in rows:
            details_map[row.id] = self._build_details(row)
        for coin_id in coin_ids:
            details_map.setdefault(coin_id, self._empty_details())
        return details_map

    def get_details(self, coin_id: str) -> dict[str, object]:
        stmt = select(Coin).where(Coin.id == coin_id)
        try:
            row = self.session.execute(stmt).scalar_one_or_none()
        except OperationalError as exc:
            logger.warning("schema out-of-date: %s", exc)
            return self._empty_details()
        return self._build_details(row)

    def get_categories_with_timestamps(
        self, coin_ids: list[str]
    ) -> dict[str, tuple[list[str], list[str], dict[str, str], dt.datetime | None]]:
        if not coin_ids:
            return {}
        stmt = select(
            Coin.id,
            Coin.category_names,
            Coin.category_ids,
            Coin.social_links,
            Coin.updated_at,
        ).where(Coin.id.in_(coin_ids))
        try:
            rows = self.session.execute(stmt).all()
        except OperationalError as exc:
            logger.warning("schema out-of-date: %s", exc)
            return {cid: ([], [], {}, None) for cid in coin_ids}
        result: dict[str, tuple[list[str], list[str], dict[str, str], dt.datetime | None]] = {}
        for cid, names_raw, ids_raw, links_raw, ts in rows:
            names = json.loads(names_raw) if names_raw else []
            ids = json.loads(ids_raw) if ids_raw else []
            if links_raw:
                try:
                    links = json.loads(links_raw)
                    if not isinstance(links, dict):
                        links = {}
                except json.JSONDecodeError:
                    links = {}
            else:
                links = {}
            if names_raw is None or ids_raw is None:
                ts = None
            if ts is not None and ts.tzinfo is None:
                ts = ts.replace(tzinfo=dt.timezone.utc)
            result[cid] = (names, ids, links, ts)
        return result

    def get_categories_with_timestamp(
        self, coin_id: str
    ) -> tuple[list[str], list[str], dict[str, str], dt.datetime | None]:
        stmt = select(
            Coin.category_names,
            Coin.category_ids,
            Coin.social_links,
            Coin.updated_at,
        ).where(
            Coin.id == coin_id
        )
        try:
            row = self.session.execute(stmt).first()
        except OperationalError as exc:
            logger.warning("schema out-of-date: %s", exc)
            return [], [], {}, None
        if not row:
            return [], [], {}, None
        names_raw, ids_raw, links_raw, ts = row
        names = json.loads(names_raw) if names_raw else []
        ids = json.loads(ids_raw) if ids_raw else []
        if links_raw:
            try:
                links = json.loads(links_raw)
                if not isinstance(links, dict):
                    links = {}
            except json.JSONDecodeError:
                links = {}
        else:
            links = {}
        if names_raw is None or ids_raw is None:
            ts = None
        if ts is not None and ts.tzinfo is None:
            ts = ts.replace(tzinfo=dt.timezone.utc)
        return names, ids, links, ts

    def list_category_issues(
        self,
        *,
        now: dt.datetime | None = None,
        stale_after: dt.timedelta = dt.timedelta(hours=24),
    ) -> list[dict[str, object]]:
        """Return coins with empty categories or outdated timestamps."""

        try:
            rows = self.session.execute(
                select(Coin.id, Coin.category_names, Coin.updated_at)
            ).all()
        except OperationalError as exc:
            logger.warning("schema out-of-date: %s", exc)
            return []

        reference = now or dt.datetime.now(dt.timezone.utc)
        if reference.tzinfo is None:
            reference = reference.replace(tzinfo=dt.timezone.utc)

        safe_delta = stale_after if stale_after.total_seconds() > 0 else dt.timedelta(0)
        threshold = reference - safe_delta

        issues: list[dict[str, object]] = []
        for coin_id, names_raw, updated_at in rows:
            names: list[str]
            if names_raw:
                try:
                    parsed = json.loads(names_raw)
                    names = list(parsed) if isinstance(parsed, list) else []
                except Exception:  # pragma: no cover - defensive
                    names = []
            else:
                names = []

            reasons: list[str] = []
            if not names:
                reasons.append("missing_categories")

            timestamp = updated_at
            if timestamp is not None and timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=dt.timezone.utc)

            if timestamp is None or timestamp < threshold:
                reasons.append("stale_timestamp")

            if reasons:
                issues.append(
                    {
                        "coin_id": coin_id,
                        "category_names": names,
                        "updated_at": timestamp,
                        "reasons": reasons,
                    }
                )

        issues.sort(key=lambda item: item["coin_id"])
        return issues


class MetaRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, key: str) -> str | None:
        stmt = select(Meta.value).where(Meta.key == key)
        return self.session.scalar(stmt)

    def set(self, key: str, value: str) -> None:
        stmt = _upsert(self.session, Meta, [{"key": key, "value": value}])
        stmt = stmt.on_conflict_do_update(
            index_elements=[Meta.key], set_={"value": value}
        )
        self.session.execute(stmt)


class FearGreedRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    @staticmethod
    def _ensure_utc(row: FearGreed | None) -> FearGreed | None:
        if row is not None and row.timestamp is not None and row.timestamp.tzinfo is None:
            row.timestamp = row.timestamp.replace(tzinfo=dt.timezone.utc)
        return row

    def count(self) -> int:
        stmt = select(func.count()).select_from(FearGreed)
        return int(self.session.scalar(stmt) or 0)

    def get_latest(self) -> FearGreed | None:
        stmt = select(FearGreed).order_by(FearGreed.timestamp.desc()).limit(1)
        row = self.session.scalar(stmt)
        return self._ensure_utc(row)

    def get_history(
        self, since: dt.datetime | None = None
    ) -> list[FearGreed]:
        stmt = select(FearGreed)
        if since is not None:
            stmt = stmt.where(FearGreed.timestamp >= since)
        stmt = stmt.order_by(FearGreed.timestamp)
        rows = list(self.session.scalars(stmt))
        for row in rows:
            self._ensure_utc(row)
        return rows

    def upsert_many(self, rows: Iterable[dict]) -> None:
        buffered = list(rows)
        if not buffered:
            return
        stmt = _upsert(self.session, FearGreed, buffered)
        stmt = stmt.on_conflict_do_update(
            index_elements=[FearGreed.timestamp],
            set_={
                "value": stmt.excluded.value,
                "classification": stmt.excluded.classification,
                "ingested_at": stmt.excluded.ingested_at,
            },
        )
        self.session.execute(stmt)


__all__ = ["PricesRepo", "MetaRepo", "CoinsRepo", "FearGreedRepo"]
