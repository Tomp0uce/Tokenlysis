"""Database repositories."""

from __future__ import annotations

from typing import Iterable

from sqlalchemy import select, insert
from sqlalchemy.dialects.sqlite import insert as sqlite_upsert
from sqlalchemy.orm import Session

from ..models import LatestPrice, Meta, Price


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


__all__ = ["PricesRepo", "MetaRepo"]
