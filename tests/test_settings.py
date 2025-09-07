import importlib
import backend.app.core.settings as settings_module
import pytest
from pydantic import ValidationError


def test_api_key_from_env(monkeypatch):
    monkeypatch.setenv("COINGECKO_API_KEY", "env-key")
    importlib.reload(settings_module)
    assert settings_module.settings.coingecko_api_key == "env-key"
    assert settings_module.get_coingecko_headers() == {"x-cg-pro-api-key": "env-key"}


def test_empty_api_key(monkeypatch):
    monkeypatch.setenv("COINGECKO_API_KEY", "")
    importlib.reload(settings_module)
    assert settings_module.settings.coingecko_api_key is None
    assert settings_module.get_coingecko_headers() == {}


def test_cors_origins_parsing(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "http://a.com, http://b.com")
    cfg = settings_module.Settings()
    assert cfg.cors_origins == ["http://a.com", "http://b.com"]


def test_empty_cors_origins(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "")
    cfg = settings_module.Settings()
    assert cfg.cors_origins == []


def test_use_seed_on_failure_empty_is_false(monkeypatch):
    for value in ("", " "):
        monkeypatch.setenv("USE_SEED_ON_FAILURE", value)
        cfg = settings_module.Settings()
        assert cfg.use_seed_on_failure is False


def test_use_seed_on_failure_true_variants(monkeypatch):
    for value in ("true", "on", "1", "YES", " y ", "Y", "t"):
        monkeypatch.setenv("USE_SEED_ON_FAILURE", value)
        cfg = settings_module.Settings()
        assert cfg.use_seed_on_failure is True
    cfg = settings_module.Settings(use_seed_on_failure=1)
    assert cfg.use_seed_on_failure is True


def test_use_seed_on_failure_false_variants(monkeypatch):
    for value in ("false", "Off", "0"):
        monkeypatch.setenv("USE_SEED_ON_FAILURE", value)
        cfg = settings_module.Settings()
        assert cfg.use_seed_on_failure is False
    cfg = settings_module.Settings(use_seed_on_failure=0)
    assert cfg.use_seed_on_failure is False


def test_invalid_bool(monkeypatch):
    monkeypatch.setenv("USE_SEED_ON_FAILURE", "maybe")
    with pytest.raises(
        ValidationError,
        match="Invalid boolean 'maybe' for USE_SEED_ON_FAILURE",
    ):
        settings_module.Settings()


def test_int_parsing(monkeypatch):
    monkeypatch.setenv("CG_TOP_N", "")
    cfg = settings_module.Settings()
    assert cfg.cg_top_n == 20

    monkeypatch.setenv("CG_TOP_N", "abc")
    with pytest.raises(ValueError, match="Invalid integer 'abc' for CG_TOP_N"):
        settings_module.Settings()


def test_log_level_parsing(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "")
    cfg = settings_module.Settings()
    assert cfg.log_level is None

    monkeypatch.setenv("LOG_LEVEL", " INFO ")
    cfg = settings_module.Settings()
    assert cfg.log_level == "INFO"

    monkeypatch.setenv("LOG_LEVEL", "15")
    cfg = settings_module.Settings()
    assert cfg.log_level == 15


def test_mask_secret():
    assert settings_module.mask_secret("abcdef1234") == "******1234"
