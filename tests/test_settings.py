import importlib

import backend.app.core.settings as settings_module


def test_api_key_from_env(monkeypatch):
    monkeypatch.setenv("COINGECKO_API_KEY", "env-key")
    importlib.reload(settings_module)
    assert settings_module.COINGECKO_API_KEY == "env-key"
    assert settings_module.get_coingecko_headers() == {"x-cg-pro-api-key": "env-key"}


def test_cors_origins_parsing(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "http://a.com, http://b.com")
    cfg = settings_module.Settings()
    assert cfg.cors_origins == ["http://a.com", "http://b.com"]


def test_empty_cors_origins(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "")
    cfg = settings_module.Settings()
    assert cfg.cors_origins == []
