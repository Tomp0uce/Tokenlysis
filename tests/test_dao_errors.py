from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import OperationalError

from backend.app.db import Base
from backend.app.services.dao import CoinsRepo


def _setup_db(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path/'test.db'}", connect_args={"check_same_thread": False}
    )
    TestingSessionLocal = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
    )
    Base.metadata.create_all(bind=engine)
    return TestingSessionLocal


def test_get_categories_with_timestamp_handles_operational_error(
    monkeypatch, tmp_path, caplog
):
    TestingSessionLocal = _setup_db(tmp_path)
    session = TestingSessionLocal()
    repo = CoinsRepo(session)

    def boom(*args, **kwargs):
        raise OperationalError("stmt", {}, "err")

    monkeypatch.setattr(session, "execute", boom)
    with caplog.at_level("WARNING"):
        names, ids, links, ts = repo.get_categories_with_timestamp("btc")
    assert names == []
    assert ids == []
    assert links == {}
    assert ts is None
    assert "schema out-of-date" in caplog.text
    session.close()


def test_get_categories_bulk_handles_operational_error(monkeypatch, tmp_path, caplog):
    TestingSessionLocal = _setup_db(tmp_path)
    session = TestingSessionLocal()
    repo = CoinsRepo(session)

    def boom(*args, **kwargs):
        raise OperationalError("stmt", {}, "err")

    monkeypatch.setattr(session, "execute", boom)
    with caplog.at_level("WARNING"):
        result = repo.get_categories_bulk(["btc", "eth"])
    assert result == {"btc": ([], []), "eth": ([], [])}
    assert "schema out-of-date" in caplog.text
    session.close()


def test_get_categories_with_timestamps_handles_operational_error(
    monkeypatch, tmp_path, caplog
):
    TestingSessionLocal = _setup_db(tmp_path)
    session = TestingSessionLocal()
    repo = CoinsRepo(session)

    def boom(*args, **kwargs):
        raise OperationalError("stmt", {}, "err")

    monkeypatch.setattr(session, "execute", boom)
    coin_ids = ["btc", "eth"]
    with caplog.at_level("WARNING"):
        result = repo.get_categories_with_timestamps(coin_ids)
    assert result == {cid: ([], [], {}, None) for cid in coin_ids}
    assert "schema out-of-date" in caplog.text
    session.close()
