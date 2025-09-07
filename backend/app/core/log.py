"""Logging utilities."""

from __future__ import annotations

import contextvars
import logging

logger = logging.getLogger("tokenlysis")
request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="-"
)

__all__ = ["logger", "request_id_ctx"]
