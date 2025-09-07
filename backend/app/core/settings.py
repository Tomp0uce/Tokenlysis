from __future__ import annotations

from typing import Any, List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def mask_secret(value: str | None) -> str:
    """Mask a secret leaving only the last four characters visible."""

    if not value:
        return ""
    if len(value) <= 4:
        return "*" * len(value)
    return "*" * (len(value) - 4) + value[-4:]


TRUE_VALUES = {"1", "true", "t", "yes", "y", "on"}
FALSE_VALUES = {"0", "false", "f", "no", "n", "off"}


def _coerce_bool(value: Any, default: bool, env_name: str) -> bool:
    if value is None:
        return default
    if isinstance(value, str):
        s = value.strip()
        if s == "":
            return default
        sl = s.lower()
        if sl in TRUE_VALUES:
            return True
        if sl in FALSE_VALUES:
            return False
        raise ValueError(f"Invalid boolean '{value}' for {env_name}")
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        if value in (0, 1):
            return bool(value)
        raise ValueError(f"Invalid boolean integer '{value}' for {env_name}")
    raise ValueError(f"Invalid boolean type '{type(value).__name__}' for {env_name}")


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
    coingecko_api_key: str | None = Field(
        default=None,
        description="CoinGecko API key",
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
    def _coerce_empty_bool(cls, v: Any, info) -> Any:  # type: ignore[override]
        default = cls.model_fields[info.field_name].default
        env_name = info.field_name.upper()
        return _coerce_bool(v, default, env_name)

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
        return s.upper()

    @field_validator("coingecko_api_key", mode="before")
    @classmethod
    def _empty_api_key(cls, v: Any) -> Any:
        if isinstance(v, str) and v.strip() == "":
            return None
        return v


settings = Settings()


def get_coingecko_headers() -> dict[str, str]:
    """Return CoinGecko API headers if an API key is available."""
    if settings.coingecko_api_key:
        return {"x-cg-pro-api-key": settings.coingecko_api_key}
    return {}


__all__ = [
    "Settings",
    "settings",
    "get_coingecko_headers",
    "mask_secret",
]
