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


def _coerce_bool(value: Any, default: bool) -> bool:
    """Coerce various inputs to bool, falling back to default when unknown."""

    if value is None:
        return default

    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        s = value.strip()
        if s == "":
            return default
        sl = s.lower()
        if sl in TRUE_VALUES:
            return True
        if sl in FALSE_VALUES:
            return False
        return default

    try:
        return bool(int(value))
    except Exception:  # pragma: no cover - defensive
        return default


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
    COINGECKO_API_KEY: str | None = None
    coingecko_api_key: str | None = Field(default=None, alias="coingecko_api_key")
    CG_TOP_N: int = 100
    CG_DAYS: int = 14
    CG_INTERVAL: str | None = "daily"
    CG_THROTTLE_MS: int = 150
    use_seed_on_failure: bool = Field(
        default=True, description="Use seed data when ETL fails"
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
    def _v_use_seed_on_failure(cls, v: Any, info) -> bool:  # type: ignore[override]
        default = cls.model_fields[info.field_name].default
        return _coerce_bool(v, default)

    @field_validator("CG_TOP_N", "CG_DAYS", "CG_THROTTLE_MS", mode="before")
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

    @field_validator("COINGECKO_API_KEY", "coingecko_api_key", mode="before")
    @classmethod
    def _empty_api_key(cls, v: Any) -> Any:
        if isinstance(v, str):
            s = v.strip()
            if s == "":
                return None
            return s
        return v


settings = Settings()


def get_coingecko_headers() -> dict[str, str]:
    """Return CoinGecko API headers if an API key is available."""
    key = settings.COINGECKO_API_KEY or settings.coingecko_api_key
    return {"x-cg-pro-api-key": key} if key else {}


def effective_coingecko_base_url() -> str:
    """Return the CoinGecko base URL depending on API key presence."""
    key = settings.COINGECKO_API_KEY or settings.coingecko_api_key
    return (
        "https://pro-api.coingecko.com/api/v3"
        if key
        else "https://api.coingecko.com/api/v3"
    )


__all__ = [
    "Settings",
    "settings",
    "get_coingecko_headers",
    "effective_coingecko_base_url",
    "mask_secret",
]
