"""Database repositories."""

from __future__ import annotations

import datetime as dt
from typing import Iterable
import logging

from sqlalchemy import select, insert
from sqlalchemy.exc import OperationalError
from sqlalchemy.dialects.sqlite import insert as sqlite_upsert
from sqlalchemy.orm import Session

from ..models import Coin, LatestPrice, Meta, Price

logger = logging.getLogger(__name__)


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

    def upsert_latest(self, rows: Iterable[dict]) -> None:
        if not rows:
            return
        stmt = sqlite_upsert(LatestPrice).values(list(rows))
        stmt = stmt.on_conflict_do_update(
            index_elements=[LatestPrice.coin_id, LatestPrice.vs_currency],
            set_={
                "price": stmt.excluded.price,
                "market_cap": stmt.excluded.market_cap,
                "volume_24h": stmt.excluded.volume_24h,
                "rank": stmt.excluded.rank,
                "pct_change_24h": stmt.excluded.pct_change_24h,
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

    def upsert(self, rows: Iterable[dict]) -> None:
        if not rows:
            return
        stmt = sqlite_upsert(Coin).values(list(rows))
        stmt = stmt.on_conflict_do_update(
            index_elements=[Coin.id],
            set_={
                "symbol": stmt.excluded.symbol,
                "name": stmt.excluded.name,
                "category_names": stmt.excluded.category_names,
                "category_ids": stmt.excluded.category_ids,
                "updated_at": stmt.excluded.updated_at,
            },
        )
        self.session.execute(stmt)

    def get_categories(self, coin_id: str) -> tuple[list[str], list[str]]:
        stmt = select(Coin.category_names, Coin.category_ids).where(Coin.id == coin_id)
        row = self.session.execute(stmt).first()
        if not row:
            return [], []
        import json

        names = json.loads(row[0]) if row[0] else []
        ids = json.loads(row[1]) if row[1] else []
        return names, ids

    def get_categories_bulk(
        self, coin_ids: list[str]
    ) -> dict[str, tuple[list[str], list[str]]]:
        if not coin_ids:
            return {}
        stmt = select(Coin.id, Coin.category_names, Coin.category_ids).where(
            Coin.id.in_(coin_ids)
        )
        try:
            rows = self.session.execute(stmt).all()
        except OperationalError as exc:
            logger.warning("schema out-of-date: %s", exc)
            return {cid: ([], []) for cid in coin_ids}
        import json

        return {
            r[0]: (
                json.loads(r[1]) if r[1] else [],
                json.loads(r[2]) if r[2] else [],
            )
            for r in rows
        }

    def get_categories_with_timestamps(
        self, coin_ids: list[str]
    ) -> dict[str, tuple[list[str], list[str], dt.datetime | None]]:
        if not coin_ids:
            return {}
        stmt = select(
            Coin.id, Coin.category_names, Coin.category_ids, Coin.updated_at
        ).where(Coin.id.in_(coin_ids))
        try:
            rows = self.session.execute(stmt).all()
        except OperationalError as exc:
            logger.warning("schema out-of-date: %s", exc)
            return {cid: ([], [], None) for cid in coin_ids}
        import json

        result: dict[str, tuple[list[str], list[str], dt.datetime | None]] = {}
        for cid, names_raw, ids_raw, ts in rows:
            names = json.loads(names_raw) if names_raw else []
            ids = json.loads(ids_raw) if ids_raw else []
            if names_raw is None or ids_raw is None:
                ts = None
            if ts is not None and ts.tzinfo is None:
                ts = ts.replace(tzinfo=dt.timezone.utc)
            result[cid] = (names, ids, ts)
        return result

    def get_categories_with_timestamp(
        self, coin_id: str
    ) -> tuple[list[str], list[str], dt.datetime | None]:
        stmt = select(Coin.category_names, Coin.category_ids, Coin.updated_at).where(
            Coin.id == coin_id
        )
        try:
            row = self.session.execute(stmt).first()
        except OperationalError as exc:
            logger.warning("schema out-of-date: %s", exc)
            return [], [], None
        if not row:
            return [], [], None
        import json

        names_raw, ids_raw, ts = row
        names = json.loads(names_raw) if names_raw else []
        ids = json.loads(ids_raw) if ids_raw else []
        if names_raw is None or ids_raw is None:
            ts = None
        if ts is not None and ts.tzinfo is None:
            ts = ts.replace(tzinfo=dt.timezone.utc)
        return names, ids, ts


class MetaRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, key: str) -> str | None:
        stmt = select(Meta.value).where(Meta.key == key)
        return self.session.scalar(stmt)

    def set(self, key: str, value: str) -> None:
        stmt = sqlite_upsert(Meta).values({"key": key, "value": value})
        stmt = stmt.on_conflict_do_update(
            index_elements=[Meta.key], set_={"value": value}
        )
        self.session.execute(stmt)


__all__ = ["PricesRepo", "MetaRepo", "CoinsRepo"]
