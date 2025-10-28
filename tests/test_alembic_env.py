import importlib
import inspect
import sys
from types import SimpleNamespace

import pytest


class DummyTransaction:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class StubContext:
    def __init__(self):
        self.configure_calls = []
        self.transactions_started = 0
        self.run_migrations_called = 0
        self.config = None

    def configure(self, *args, **kwargs):
        self.configure_calls.append((args, kwargs))

    def begin_transaction(self):
        self.transactions_started += 1
        return DummyTransaction()

    def run_migrations(self):
        self.run_migrations_called += 1


@pytest.fixture
def env_module(monkeypatch):
    from alembic import context as alembic_context

    stub_context = StubContext()
    stub_config = SimpleNamespace(
        config_ini_section="alembic",
        get_section=lambda section_name: {},
        get_main_option=lambda option_name: "config://fallback",
        config_file_name=None,
    )
    stub_context.config = stub_config

    monkeypatch.setattr(alembic_context, "config", stub_config, raising=False)
    monkeypatch.setattr(alembic_context, "configure", stub_context.configure, raising=False)
    monkeypatch.setattr(
        alembic_context, "begin_transaction", stub_context.begin_transaction, raising=False
    )
    monkeypatch.setattr(alembic_context, "run_migrations", stub_context.run_migrations, raising=False)
    monkeypatch.setattr(alembic_context, "is_offline_mode", lambda: True, raising=False)

    sys.modules.pop("backend.alembic.env", None)
    module = importlib.import_module("backend.alembic.env")

    stub_context.configure_calls.clear()
    stub_context.transactions_started = 0
    stub_context.run_migrations_called = 0

    monkeypatch.setattr(module, "context", stub_context, raising=False)
    monkeypatch.setattr(module, "config", stub_config, raising=False)

    return module, stub_context, stub_config


def test_get_db_url_prefers_alembic_env(monkeypatch, env_module):
    module, _, stub_config = env_module
    monkeypatch.setenv("ALEMBIC_DATABASE_URL", "sqlite:///env.db")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    stub_config.get_main_option = lambda name: "config://fallback"

    assert module._get_db_url() == "sqlite:///env.db"


def test_get_db_url_falls_back_to_database_url(monkeypatch, env_module):
    module, _, stub_config = env_module
    monkeypatch.delenv("ALEMBIC_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "sqlite:///db.db")
    stub_config.get_main_option = lambda name: "config://fallback"

    assert module._get_db_url() == "sqlite:///db.db"


def test_get_db_url_uses_config_when_env_missing(monkeypatch, env_module):
    module, _, stub_config = env_module
    monkeypatch.delenv("ALEMBIC_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    stub_config.get_main_option = lambda name: "sqlite:///from-config.db"

    assert module._get_db_url() == "sqlite:///from-config.db"


def test_is_sqlite_detects_sqlite(env_module):
    module, _, _ = env_module
    assert module._is_sqlite("sqlite:///example.db")
    assert not module._is_sqlite("postgresql+psycopg://user@localhost/db")


def test_run_migrations_offline_enables_batch_for_sqlite(monkeypatch, env_module):
    module, stub_context, stub_config = env_module
    monkeypatch.setenv("ALEMBIC_DATABASE_URL", "sqlite:///offline.db")
    stub_context.configure_calls.clear()

    module.run_migrations_offline()

    assert stub_context.configure_calls
    _, kwargs = stub_context.configure_calls[-1]
    assert kwargs["render_as_batch"] is True


def test_run_migrations_offline_disables_batch_for_non_sqlite(monkeypatch, env_module):
    module, stub_context, stub_config = env_module
    monkeypatch.setenv("ALEMBIC_DATABASE_URL", "postgresql+psycopg://user@localhost/db")
    stub_context.configure_calls.clear()

    module.run_migrations_offline()

    assert stub_context.configure_calls
    _, kwargs = stub_context.configure_calls[-1]
    assert kwargs["render_as_batch"] is False


def test_run_migrations_online_uses_sync_engine(monkeypatch, env_module):
    module, stub_context, stub_config = env_module
    monkeypatch.setenv("ALEMBIC_DATABASE_URL", "sqlite:///online.db")

    captured = {}

    class DummyConnection(DummyTransaction):
        def __init__(self):
            self.dialect = SimpleNamespace(name="sqlite")

        def connect(self):
            return self

    class DummyEngine:
        def connect(self):
            return DummyConnection()

    def fake_engine_from_config(section, prefix, poolclass, future):
        captured["section"] = section
        captured["prefix"] = prefix
        captured["poolclass"] = poolclass
        captured["future"] = future
        return DummyEngine()

    monkeypatch.setattr(module, "engine_from_config", fake_engine_from_config)

    module.run_migrations_online()

    assert captured["prefix"] == "sqlalchemy."
    assert captured["poolclass"].__name__ == "NullPool"
    assert captured["future"] is True

    assert stub_context.configure_calls
    _, kwargs = stub_context.configure_calls[-1]
    assert kwargs["render_as_batch"] is True
    assert stub_context.transactions_started == 1
    assert stub_context.run_migrations_called == 1


def test_env_module_exposes_only_sync_engine(env_module):
    module, _, _ = env_module

    assert not hasattr(module, "async_engine_from_config")
    assert hasattr(module, "engine_from_config")


def test_alembic_ini_uses_env_var_only():
    from pathlib import Path

    lines = Path("alembic.ini").read_text().splitlines()

    url_lines = [line.strip() for line in lines if line.strip().startswith("sqlalchemy.url")]
    assert url_lines == ["sqlalchemy.url = ${ALEMBIC_DATABASE_URL}"]
    assert all("sqlite:///" not in line for line in lines)


def test_env_module_has_no_create_all(env_module):
    module, _, _ = env_module

    source = inspect.getsource(module)

    assert "create_all(" not in source
