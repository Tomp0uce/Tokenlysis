from __future__ import annotations

import os
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY")


class Settings(BaseSettings):
    """Application settings loaded from environment."""

    cors_origins: List[str] | str = ["http://localhost"]
    cg_top_n: int = 20
    cg_days: int = 14

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v: str | List[str]) -> List[str]:
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v


settings = Settings()


def get_coingecko_headers() -> dict[str, str]:
    """Return CoinGecko API headers if an API key is available."""

    if COINGECKO_API_KEY:
        return {"x-cg-pro-api-key": COINGECKO_API_KEY}
    return {}


__all__ = ["Settings", "settings", "get_coingecko_headers", "COINGECKO_API_KEY"]
