from __future__ import annotations

from functools import lru_cache

import casbin

from .config import get_settings


@lru_cache(1)
def get_enforcer() -> casbin.Enforcer:
    settings = get_settings()
    return casbin.Enforcer(settings.casbin_model_path, settings.casbin_policy_path)


def authorize(subject: str, obj: str, action: str) -> bool:
    enforcer = get_enforcer()
    return enforcer.enforce(subject, obj, action)
