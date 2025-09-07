import importlib
import pytest

import backend.app.core.settings as settings_module


def test_api_key_from_env(monkeypatch):
    monkeypatch.setenv("COINGECKO_API_KEY", "env-key")
    monkeypatch.delenv("COINGECKO_PLAN", raising=False)
    importlib.reload(settings_module)
    assert settings_module.settings.COINGECKO_API_KEY == "env-key"
    assert settings_module.get_coingecko_headers() == {"x-cg-demo-api-key": "env-key"}
    assert (
        settings_module.effective_coingecko_base_url()
        == "https://api.coingecko.com/api/v3"
    )


def test_lowercase_api_key(monkeypatch):
    monkeypatch.delenv("COINGECKO_API_KEY", raising=False)
    monkeypatch.setenv("coingecko_api_key", "low-key")
    monkeypatch.setenv("COINGECKO_PLAN", "pro")
    importlib.reload(settings_module)
    assert settings_module.settings.coingecko_api_key == "low-key"
    assert settings_module.get_coingecko_headers() == {"x-cg-pro-api-key": "low-key"}


def test_effective_base_url_without_api_key(monkeypatch):
    monkeypatch.delenv("COINGECKO_API_KEY", raising=False)
    monkeypatch.delenv("coingecko_api_key", raising=False)
    monkeypatch.delenv("COINGECKO_PLAN", raising=False)
    importlib.reload(settings_module)
    assert (
        settings_module.effective_coingecko_base_url()
        == "https://api.coingecko.com/api/v3"
    )


def test_empty_api_key(monkeypatch):
    monkeypatch.setenv("COINGECKO_API_KEY", "")
    importlib.reload(settings_module)
    assert settings_module.settings.COINGECKO_API_KEY is None
    assert settings_module.get_coingecko_headers() == {}


def test_cors_origins_parsing(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "http://a.com, http://b.com")
    cfg = settings_module.Settings()
    assert cfg.cors_origins == ["http://a.com", "http://b.com"]


def test_empty_cors_origins(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "")
    cfg = settings_module.Settings()
    assert cfg.cors_origins == []


def test_use_seed_on_failure_empty_is_true(monkeypatch):
    for value in ("", " "):
        monkeypatch.setenv("USE_SEED_ON_FAILURE", value)
        cfg = settings_module.Settings()
        assert cfg.use_seed_on_failure is True


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


def test_use_seed_on_failure_invalid_falls_back(monkeypatch):
    monkeypatch.setenv("USE_SEED_ON_FAILURE", "maybe")
    cfg = settings_module.Settings()
    assert cfg.use_seed_on_failure is True


def test_int_parsing(monkeypatch):
    monkeypatch.setenv("CG_TOP_N", "")
    cfg = settings_module.Settings()
    assert cfg.CG_TOP_N == 100

    monkeypatch.setenv("CG_TOP_N", "abc")
    with pytest.raises(ValueError, match="Invalid integer 'abc' for CG_TOP_N"):
        settings_module.Settings()


def test_cg_days_parsing(monkeypatch):
    monkeypatch.setenv("CG_DAYS", "")
    cfg = settings_module.Settings()
    assert cfg.CG_DAYS == 14

    monkeypatch.setenv("CG_DAYS", "abc")
    with pytest.raises(ValueError, match="Invalid integer 'abc' for CG_DAYS"):
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


def test_log_level_unknown_no_crash(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "foo")
    cfg = settings_module.Settings()
    assert cfg.log_level == "FOO"


def test_coerce_bool_helper():
    from backend.app.core.settings import _coerce_bool

    assert _coerce_bool("", False) is False
    assert _coerce_bool(" YES ", False) is True
    assert _coerce_bool("maybe", True) is True


def test_mask_secret():
    assert settings_module.mask_secret("abcdef1234") == "******1234"
