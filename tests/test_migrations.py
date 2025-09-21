import sqlite3
from pathlib import Path

from backend.app.core.settings import settings as settings_module
from backend.app.db.migrations import run_migrations


def test_run_migrations_uses_settings_db(monkeypatch, tmp_path):
    db_path = tmp_path / "migr.db"
    monkeypatch.setattr(settings_module, "DATABASE_URL", f"sqlite:///{db_path}")
    run_migrations()
    assert db_path.exists()
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    cur.execute("PRAGMA table_info(coins)")
    cols = [row[1] for row in cur.fetchall()]
    assert "category_names" in cols
    assert "category_ids" in cols
    assert "social_links" in cols
    con.close()


def test_run_migrations_falls_back_to_config(monkeypatch):
    db_path = Path("tokenlysis.db")
    if db_path.exists():
        db_path.unlink()
    monkeypatch.setattr(settings_module, "DATABASE_URL", "")
    try:
        run_migrations()
        assert db_path.exists()
    finally:
        if db_path.exists():
            db_path.unlink()
