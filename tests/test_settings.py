from pathlib import Path

from backend.app.core.settings import Settings, get_coingecko_headers


def test_api_key_from_env(monkeypatch):
    monkeypatch.setenv("COINGECKO_API_KEY", "env-key")
    cfg = Settings()
    assert cfg.coingecko_api_key == "env-key"
    assert get_coingecko_headers(cfg) == {"x-cg-pro-api-key": "env-key"}


def test_api_key_from_secret_file(monkeypatch):
    monkeypatch.delenv("COINGECKO_API_KEY", raising=False)
    secrets_dir = Path("/run/secrets")
    secrets_dir.mkdir(parents=True, exist_ok=True)
    secret_file = secrets_dir / "COINGECKO_API_KEY"
    secret_file.write_text("file-key\n")
    try:
        cfg = Settings()
        assert cfg.coingecko_api_key == "file-key"
        assert get_coingecko_headers(cfg) == {"x-cg-pro-api-key": "file-key"}
    finally:
        secret_file.unlink()


def test_cors_origins_parsing(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "http://a.com, http://b.com")
    cfg = Settings()
    assert cfg.cors_origins == ["http://a.com", "http://b.com"]


def test_empty_cors_origins(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "")
    cfg = Settings()
    assert cfg.cors_origins == []
