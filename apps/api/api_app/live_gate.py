from __future__ import annotations

import os

P21_LIVE_PORTAL_GATE_ENV = "P21_LIVE_PORTAL_GATE"
P21_LIVE_PORTAL_REQUIRED_ENV_MISSING = "P21_LIVE_PORTAL_REQUIRED_ENV_MISSING"
P21_LIVE_PLF_UNAVAILABLE = "P21_LIVE_PLF_UNAVAILABLE"
P21_LIVE_PPM_REQUIRED = "P21_LIVE_PPM_REQUIRED"


def env_flag(name: str, *, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def p21_live_portal_enabled() -> bool:
    return env_flag(P21_LIVE_PORTAL_GATE_ENV)
