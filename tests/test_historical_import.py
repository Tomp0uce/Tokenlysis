import datetime as dt
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.db import Base
from backend.app.models import Coin, Price


def _setup_session(tmp_path: Path) -> sessionmaker:
    engine = create_engine(
        f"sqlite:///{tmp_path/'hist.db'}", connect_args={"check_same_thread": False}
    )
    TestingSession = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
    )
    Base.metadata.create_all(bind=engine)
    return TestingSession


def _write_csv(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                '"Date,""Open"",""High"",""Low"",""Close"",""Volume"",""ticker"",""name"""',
                '"2024-01-01 00:00:00+00:00,""1"",""1"",""1"",""2.5"",""123"",""AAA-USD"",""Alpha"""',
                '"2024-01-02 00:00:00+00:00,""1"",""1"",""1"",""4"",""456"",""AAA-USD"",""ALPHA"""',
                '"invalid,""1"",""1"",""1"",""5"",""789"",""AAA-USD"",""Alpha"""',
                '"2024-01-01 00:00:00+00:00,""1"",""1"",""1"",""3"",""999"",""BBB-USD"",""Missing Coin"""',
            ]
        )
        + "\n"
    )


def test_import_historical_data_inserts_prices(tmp_path):
    TestingSession = _setup_session(tmp_path)
    csv_path = tmp_path / "hist.csv"
    _write_csv(csv_path)

    from backend.app.etl import historical_import

    session = TestingSession()
    session.add(Coin(id="alpha", symbol="AAA", name="Alpha"))
    session.commit()

    inserted = historical_import.import_historical_data(session, [csv_path])

    rows = session.execute(select(Price)).scalars().all()
    assert inserted == 2
    assert len(rows) == 2

    def _normalize(ts: dt.datetime) -> dt.datetime:
        return ts if ts.tzinfo is not None else ts.replace(tzinfo=dt.timezone.utc)

    by_date = {_normalize(row.snapshot_at): row for row in rows}
    first_ts = dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc)
    second_ts = dt.datetime(2024, 1, 2, tzinfo=dt.timezone.utc)

    assert by_date[first_ts].price == 2.5
    assert by_date[first_ts].volume_24h == 123
    assert by_date[second_ts].price == 4
    assert by_date[second_ts].volume_24h == 456

    session.close()


def test_import_historical_data_skips_unknown_coins(tmp_path):
    TestingSession = _setup_session(tmp_path)
    csv_path = tmp_path / "hist.csv"
    _write_csv(csv_path)

    from backend.app.etl import historical_import

    session = TestingSession()
    session.add(Coin(id="beta", symbol="BBB", name="Beta"))
    session.commit()

    inserted = historical_import.import_historical_data(session, [csv_path])

    rows = session.execute(select(Price)).scalars().all()
    assert inserted == 0
    assert rows == []

    session.close()

