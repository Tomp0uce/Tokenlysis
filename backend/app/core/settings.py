from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment and optional files."""

    cors_origins: List[str] = ["http://localhost"]
    cg_top_n: int = 20
    cg_days: int = 14
    coingecko_api_key: Optional[str] = None

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v: str | List[str]) -> List[str]:
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v

    @field_validator("coingecko_api_key", mode="before")
    @classmethod
    def _load_coingecko_key(cls, v: Optional[str]) -> Optional[str]:
        if v:
            return v.strip()
        env_key = os.environ.get("COINGECKO_API_KEY")
        if env_key:
            return env_key.strip()
        secret_path = Path("/run/secrets/COINGECKO_API_KEY")
        if secret_path.is_file():
            try:
                return secret_path.read_text().strip()
            except OSError:
                pass
        return None


settings = Settings()


def get_coingecko_headers(settings_obj: Settings | None = None) -> dict[str, str]:
    """Return CoinGecko API headers if an API key is available."""

    cfg = settings_obj or Settings()
    if cfg.coingecko_api_key:
        return {"x-cg-pro-api-key": cfg.coingecko_api_key}
    return {}


__all__ = ["Settings", "settings", "get_coingecko_headers"]
