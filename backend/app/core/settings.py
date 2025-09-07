from __future__ import annotations

import os
from typing import Any, List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY") or None


def mask_secret(value: str | None) -> str:
    """Mask a secret leaving only the last four characters visible."""

    if not value:
        return ""
    if len(value) <= 4:
        return "*" * len(value)
    return "*" * (len(value) - 4) + value[-4:]


TRUE_VALUES = {"true", "1", "yes", "on"}
FALSE_VALUES = {"false", "0", "no", "off"}


def _parse_bool(value: Any, env_name: str, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, str):
        stripped = value.strip()
        if stripped == "":
            return default
        lowered = stripped.lower()
        if lowered in TRUE_VALUES:
            return True
        if lowered in FALSE_VALUES:
            return False
    elif isinstance(value, bool):
        return value
    raise ValueError(f"Invalid boolean '{value}' for {env_name}")


def _parse_int(value: Any, env_name: str, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, str):
        stripped = value.strip()
        if stripped == "":
            return default
        value = stripped
    try:
        return int(value)
    except (TypeError, ValueError) as exc:  # pragma: no cover
        raise ValueError(f"Invalid integer '{value}' for {env_name}") from exc


class Settings(BaseSettings):
    """Application settings loaded from environment."""

    cors_origins: List[str] | str = ["http://localhost"]
    cg_top_n: int = 20
    cg_days: int = 14
    use_seed_on_failure: bool = Field(
        default=False, description="Use seed data when ETL fails"
    )
    log_level: str | int | None = Field(
        default=None, description="Python logging level"
    )

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v: str | List[str]) -> List[str]:
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v

    @field_validator("use_seed_on_failure", mode="before")
    @classmethod
    def _validate_bool(cls, v: Any) -> bool:
        default = cls.model_fields["use_seed_on_failure"].default
        return _parse_bool(v, "USE_SEED_ON_FAILURE", default)

    @field_validator("cg_top_n", "cg_days", mode="before")
    @classmethod
    def _validate_int(cls, v: Any, info) -> int:  # type: ignore[override]
        default = cls.model_fields[info.field_name].default
        env_name = info.field_name.upper()
        return _parse_int(v, env_name, default)

    @field_validator("log_level", mode="before")
    @classmethod
    def _norm_log_level(cls, v: Any) -> Any:
        if v is None:
            return None
        s = str(v).strip()
        if s == "":
            return None
        if s.isdigit():
            return int(s)
        up = s.upper()
        valid = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"}
        if up in valid:
            return up
        raise ValueError(
            f"Invalid LOG_LEVEL '{s}'. Use one of {sorted(valid)} or an integer."
        )


settings = Settings()


def get_coingecko_headers() -> dict[str, str]:
    """Return CoinGecko API headers if an API key is available."""

    if COINGECKO_API_KEY:
        return {"x-cg-pro-api-key": COINGECKO_API_KEY}
    return {}


__all__ = [
    "Settings",
    "settings",
    "get_coingecko_headers",
    "COINGECKO_API_KEY",
    "mask_secret",
]
