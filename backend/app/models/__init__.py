"""ORM models for Tokenlysis."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import DateTime, Float, Integer, String, Text, Index
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class Coin(Base):
    __tablename__ = "coins"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    symbol: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    logo_url: Mapped[str | None] = mapped_column(String, nullable=True)
    category_names: Mapped[str | None] = mapped_column(Text, nullable=True)
    category_ids: Mapped[str | None] = mapped_column(Text, nullable=True)
    social_links: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class LatestPrice(Base):
    __tablename__ = "latest_prices"

    coin_id: Mapped[str] = mapped_column(String, primary_key=True)
    vs_currency: Mapped[str] = mapped_column(String, primary_key=True)
    price: Mapped[float | None] = mapped_column(Float)
    market_cap: Mapped[float | None] = mapped_column(Float)
    fully_diluted_market_cap: Mapped[float | None] = mapped_column(Float)
    volume_24h: Mapped[float | None] = mapped_column(Float)
    rank: Mapped[int | None] = mapped_column(Integer)
    pct_change_24h: Mapped[float | None] = mapped_column(Float)
    pct_change_7d: Mapped[float | None] = mapped_column(Float)
    pct_change_30d: Mapped[float | None] = mapped_column(Float)
    snapshot_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("ix_latest_prices_rank", "rank"),)


class Price(Base):
    __tablename__ = "prices"

    coin_id: Mapped[str] = mapped_column(String, primary_key=True)
    vs_currency: Mapped[str] = mapped_column(String, primary_key=True)
    snapshot_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True
    )
    price: Mapped[float | None] = mapped_column(Float)
    market_cap: Mapped[float | None] = mapped_column(Float)
    fully_diluted_market_cap: Mapped[float | None] = mapped_column(Float)
    volume_24h: Mapped[float | None] = mapped_column(Float)
    rank: Mapped[int | None] = mapped_column(Integer)
    pct_change_24h: Mapped[float | None] = mapped_column(Float)
    pct_change_7d: Mapped[float | None] = mapped_column(Float)
    pct_change_30d: Mapped[float | None] = mapped_column(Float)

    __table_args__ = (
        Index("ix_prices_snapshot_at", "snapshot_at"),
        Index("ix_prices_coin_snapshot_at", "coin_id", "snapshot_at"),
    )


class Meta(Base):
    __tablename__ = "meta"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String, nullable=False)


class FearGreed(Base):
    __tablename__ = "fear_greed_index"

    timestamp: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True
    )
    value: Mapped[int] = mapped_column(Integer, nullable=False)
    classification: Mapped[str] = mapped_column(String(64), nullable=False)
    ingested_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    __table_args__ = (Index("ix_fear_greed_timestamp", "timestamp"),)


__all__ = ["Coin", "LatestPrice", "Price", "Meta", "FearGreed"]
