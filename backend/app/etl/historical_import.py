"""One-off utilities to load historical CSV data into the database."""

from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path
from typing import Iterable, Iterator, Mapping

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from ..models import Coin, Price

_DEFAULT_DATA_DIR = Path(__file__).resolve().parents[2] / "Historical_Data"


def _iter_csv_rows(path: Path) -> Iterator[list[str]]:
    with path.open("r", encoding="utf-8") as handle:
        for raw in handle:
            cleaned = raw.strip()
            if not cleaned:
                continue
            if cleaned.startswith("\ufeff"):
                cleaned = cleaned.lstrip("\ufeff")
            if cleaned.startswith('"') and cleaned.endswith('"'):
                cleaned = cleaned[1:-1]
            cleaned = cleaned.replace('""', '"')
            try:
                row = next(csv.reader([cleaned]))
            except csv.Error:
                continue
            if row:
                yield row


def _build_coin_index(session: Session) -> Mapping[str, str]:
    rows = session.execute(select(Coin.id, Coin.name)).all()
    index: dict[str, str] = {}
    for coin_id, name in rows:
        if not name:
            continue
        index[name.casefold()] = coin_id
    return index


def _parse_timestamp(raw: str) -> dt.datetime | None:
    try:
        timestamp = dt.datetime.fromisoformat(raw)
    except ValueError:
        return None
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=dt.timezone.utc)
    return timestamp.astimezone(dt.timezone.utc)


def _to_float(raw: str) -> float | None:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _upsert_prices(session: Session, rows: list[dict[str, object]]) -> None:
    if not rows:
        return
    bind = session.get_bind()
    dialect = getattr(getattr(bind, "dialect", None), "name", "") if bind else ""
    if dialect == "sqlite":
        stmt = sqlite_insert(Price).values(rows)
    elif dialect in {"postgresql", "postgres"}:
        stmt = postgres_insert(Price).values(rows)
    else:
        raise NotImplementedError(
            "Unsupported database dialect for historical import: " f"{dialect!r}"
        )
    stmt = stmt.on_conflict_do_update(
        index_elements=[Price.coin_id, Price.vs_currency, Price.snapshot_at],
        set_={
            "price": stmt.excluded.price,
            "volume_24h": stmt.excluded.volume_24h,
        },
    )
    session.execute(stmt)


def _collect_csv_files(
    csv_files: Iterable[Path] | None = None, data_dir: Path | None = None
) -> list[Path]:
    if csv_files is not None:
        return [Path(path) for path in csv_files]
    base_dir = data_dir or _DEFAULT_DATA_DIR
    if not base_dir.exists():
        return []
    return sorted(base_dir.glob("*.csv"))


def import_historical_data(
    session: Session,
    csv_files: Iterable[Path] | None = None,
    data_dir: Path | None = None,
) -> int:
    """Load historical closing price and volume data into the database."""

    files = _collect_csv_files(csv_files, data_dir)
    if not files:
        return 0

    name_to_coin = _build_coin_index(session)
    buffered: dict[tuple[str, str, dt.datetime], dict[str, object]] = {}

    for file_path in files:
        rows_iter = _iter_csv_rows(file_path)
        try:
            header = next(rows_iter)
        except StopIteration:
            continue
        field_count = len(header)
        for row in rows_iter:
            if len(row) != field_count:
                continue
            raw_timestamp, *_rest = row
            timestamp = _parse_timestamp(raw_timestamp)
            if timestamp is None:
                continue
            close_raw = row[4]
            volume_raw = row[5]
            ticker = row[6].strip()
            name = row[7].strip()
            coin_id = name_to_coin.get(name.casefold())
            if coin_id is None:
                continue
            price = _to_float(close_raw)
            volume = _to_float(volume_raw)
            if price is None or volume is None:
                continue
            if "-" in ticker:
                vs_currency = ticker.split("-", 1)[1].lower()
            else:
                vs_currency = "usd"
            key = (coin_id, vs_currency, timestamp)
            buffered[key] = {
                "coin_id": coin_id,
                "vs_currency": vs_currency,
                "snapshot_at": timestamp,
                "price": price,
                "volume_24h": volume,
                "market_cap": None,
                "fully_diluted_market_cap": None,
                "rank": None,
                "pct_change_24h": None,
                "pct_change_7d": None,
                "pct_change_30d": None,
            }

    rows = list(buffered.values())
    if not rows:
        return 0

    _upsert_prices(session, rows)
    session.commit()
    return len(rows)


__all__ = ["import_historical_data"]
