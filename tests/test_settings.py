import importlib

import backend.app.core.settings as settings_module
import pytest


def test_api_key_from_env(monkeypatch):
    monkeypatch.setenv("COINGECKO_API_KEY", "env-key")
    importlib.reload(settings_module)
    assert settings_module.COINGECKO_API_KEY == "env-key"
    assert settings_module.get_coingecko_headers() == {"x-cg-pro-api-key": "env-key"}


def test_empty_api_key(monkeypatch):
    monkeypatch.setenv("COINGECKO_API_KEY", "")
    importlib.reload(settings_module)
    assert settings_module.COINGECKO_API_KEY is None
    assert settings_module.get_coingecko_headers() == {}


def test_cors_origins_parsing(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "http://a.com, http://b.com")
    cfg = settings_module.Settings()
    assert cfg.cors_origins == ["http://a.com", "http://b.com"]


def test_empty_cors_origins(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "")
    cfg = settings_module.Settings()
    assert cfg.cors_origins == []


@pytest.mark.parametrize(
    "value,expected",
    [
        ("", False),
        (" ", False),
        ("true", True),
        ("FALSE", False),
        ("1", True),
        ("0", False),
        ("yes", True),
        ("No", False),
    ],
)
def test_bool_parsing(monkeypatch, value, expected):
    monkeypatch.setenv("USE_SEED_ON_FAILURE", value)
    cfg = settings_module.Settings()
    assert cfg.use_seed_on_failure is expected


def test_invalid_bool(monkeypatch):
    monkeypatch.setenv("USE_SEED_ON_FAILURE", "maybe")
    with pytest.raises(
        ValueError, match="Invalid boolean 'maybe' for USE_SEED_ON_FAILURE"
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

    monkeypatch.setenv("LOG_LEVEL", "maybe")
    with pytest.raises(ValueError, match="Invalid LOG_LEVEL 'maybe'"):
        settings_module.Settings()


def test_mask_secret():
    assert settings_module.mask_secret("abcdef1234") == "******1234"

