import json
import logging

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.db import Base
from backend.app.etl import run as run_module
from backend.app.etl.run import load_seed
from backend.app.core.settings import settings


def _setup_test_session(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path/'test.db'}", connect_args={"check_same_thread": False}
    )
    TestingSessionLocal = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
    )
    Base.metadata.create_all(bind=engine)
    return TestingSessionLocal


def test_load_seed_missing_file_logs_warning(monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(settings, "SEED_FILE", str(tmp_path / "missing.json"))
    caplog.set_level(logging.WARNING, logger="backend.app.etl.run")
    # Should not raise even if file missing
    load_seed()
    assert any("seed file not found" in r.message for r in caplog.records)


def test_load_seed_logs_details(monkeypatch, tmp_path, caplog):
    TestingSessionLocal = _setup_test_session(tmp_path)
    monkeypatch.setattr(run_module, "SessionLocal", TestingSessionLocal)
    caplog.set_level(logging.INFO, logger="backend.app.etl.run")
    load_seed()
    record = next(r for r in caplog.records if r.levelno == logging.INFO)
    data = json.loads(record.message)
    assert data["seed_file"].endswith("top20.json")
    assert data["rows"] == 20
    assert data["data_source"] == "seed"
