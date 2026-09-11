"""Customer Brain flags. Brain is the permanent customer reply runtime (no enable flag)."""

from __future__ import annotations

import os
from typing import Any

_TRUTHY = frozenset({"1", "true", "yes", "on"})
_FALSY = frozenset({"0", "false", "no", "off"})


def env_flag(name: str, *, default: bool = False) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if raw in _TRUTHY:
        return True
    if raw in _FALSY:
        return False
    return default


def emergency_legacy_reply_enabled() -> bool:
    """Documented emergency switch. Default false. Never restores Luna/Terra."""
    return env_flag("EMERGENCY_LEGACY_REPLY_ENABLED")


def voyage_api_key() -> str:
    if "VOYAGE_API_KEY" in os.environ:
        return (os.environ.get("VOYAGE_API_KEY") or "").strip()
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except Exception:
        return ""
    return (os.getenv("VOYAGE_API_KEY") or "").strip()


def voyage_configured() -> bool:
    return bool(voyage_api_key())


def assert_safe_brain_cutover() -> dict[str, Any]:
    """Brain is permanent on this branch. Code rollback is the only AI restore path."""
    emergency = emergency_legacy_reply_enabled()
    return {
        "customer_engine": "brain",
        "brain_permanent": True,
        "enable_flag_removed": True,
        "emergency_legacy": emergency,
        "emergency_legacy_default": False,
        "luna_terra_restored": False,
        "rollback_required_to_leave_brain": True,
        "rollback_tag": "rollback/pre-brain-2026-09-11",
        "rollback_sha": "0f23bcf1d35886acec5dbf53eb1af2faf2734757",
        "note": (
            "CUSTOMER_BRAIN_ENABLED was removed. Customer Brain is the only customer reply "
            "engine. Redeploy the rollback tag to restore pre-Brain code; flag tricks cannot."
        ),
    }


def flags_snapshot() -> dict[str, Any]:
    cutover = assert_safe_brain_cutover()
    return {
        "voyage_configured": voyage_configured(),
        "emergency_legacy_reply_enabled": emergency_legacy_reply_enabled(),
        "customer_engine": "brain",
        "brain_permanent": True,
        "cutover": cutover,
    }
