from __future__ import annotations

import importlib

from backend.app.core import version as version_module


# T4: lecture standard depuis VERSION_FILE avec cache et rafraîchissement forcé
def test_get_version_from_file_with_cache(monkeypatch, tmp_path):
    monkeypatch.delenv("APP_VERSION", raising=False)
    version_file = tmp_path / "VERSION"
    version_file.write_text("1.0.0")
    monkeypatch.setenv("VERSION_FILE", str(version_file))
    module = importlib.reload(version_module)

    assert module.get_version(force_refresh=True) == "1.0.0"

    version_file.write_text("2.0.0")
    assert module.get_version() == "1.0.0"
    assert module.get_version(force_refresh=True) == "2.0.0"


def test_get_version_dev_env_missing_file(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_VERSION", "dev")
    missing_file = tmp_path / "VERSION"
    monkeypatch.setenv("VERSION_FILE", str(missing_file))
    module = importlib.reload(version_module)

    assert module.get_version(force_refresh=True) == "dev"


def test_get_version_defaults_to_repo_root_parent(monkeypatch, tmp_path):
    monkeypatch.delenv("APP_VERSION", raising=False)
    monkeypatch.delenv("VERSION_FILE", raising=False)
    module = importlib.reload(version_module)

    backend_dir = tmp_path / "backend"
    backend_dir.mkdir()
    version_path = tmp_path / "VERSION"
    version_path.write_text("9.9.9")

    monkeypatch.setattr(module, "REPO_ROOT", backend_dir, raising=False)
    monkeypatch.setattr(module, "_VERSION_CACHE", None, raising=False)

    assert module.get_version(force_refresh=True) == "9.9.9"
