from __future__ import annotations

import logging
from typing import Any

from fastapi import Depends, FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_fastapi_instrumentator import Instrumentator
from sentry_sdk import init as sentry_init
from sentry_sdk.integrations.asgi import SentryAsgiMiddleware

from .config import get_settings
from ..api import deps

logger = logging.getLogger(__name__)


def configure_observability(app: FastAPI) -> None:
    settings = get_settings()

    if settings.sentry_dsn:
        sentry_init(dsn=settings.sentry_dsn, environment=settings.environment)
        app.add_middleware(SentryAsgiMiddleware)

    if settings.otel_endpoint:
        resource = Resource.create({"service.name": settings.app_name})
        provider = TracerProvider(resource=resource)
        processor = BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otel_endpoint))
        provider.add_span_processor(processor)
        trace.set_tracer_provider(provider)
        logger.info("OpenTelemetry tracing configured", extra={"endpoint": settings.otel_endpoint})

    instrumentator = Instrumentator().instrument(app)
    instrumentator.expose(
        app,
        endpoint=settings.prometheus_endpoint,
        dependencies=[Depends(deps.require_role("metrics", "read"))],
    )
