from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import AnyUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="TOKENLYSIS_", extra="ignore")

    app_name: str = "Tokenlysis API"
    environment: Literal["local", "staging", "production"] = "local"

    database_url: str = Field(default="postgresql+asyncpg://postgres:postgres@localhost:5432/tokenlysis")
    alembic_location: str = "backend/alembic"

    redis_url: str = "redis://localhost:6379/0"

    oidc_issuer: AnyUrl = Field(default="https://auth.localhost/realms/tokenlysis")
    oidc_audience: str = "tokenlysis-api"
    oidc_client_id: str = "tokenlysis-api"

    casbin_model_path: str = Field(default="backend/app/core/rbac_model.conf")
    casbin_policy_path: str = Field(default="backend/app/core/rbac_policy.csv")

    sentry_dsn: str | None = None
    otel_endpoint: str | None = None

    s3_endpoint: AnyUrl = Field(default="https://minio.localhost")
    s3_access_key: str = "minio"
    s3_secret_key: str = "minio123"
    s3_bucket: str = "tokenlysis"

    prometheus_endpoint: str = "/metrics"

    admin_secret: str = "change-me"


@lru_cache(1)
def get_settings() -> Settings:
    return Settings()
