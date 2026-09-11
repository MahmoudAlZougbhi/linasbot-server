"""Customer Brain enablement. Default off — not a live-customer switch."""

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


def customer_brain_enabled() -> bool:
    return env_flag("CUSTOMER_BRAIN_ENABLED")


def emergency_legacy_reply_enabled() -> bool:
    """Temporary documented switch. Default false.

    Never restores Luna/Terra. When Brain is OFF and this is true, the runtime
    still fails closed with ``emergency_legacy_unavailable``. Honest AI restore
    is redeploy of rollback tag ``rollback/pre-brain-2026-09-11`` → ``0f23bcf1``.
    """
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
    """Hard deploy gate matrix. Emergency legacy stays false by default."""
    brain_on = customer_brain_enabled()
    emergency = emergency_legacy_reply_enabled()
    return {
        "brain_on": brain_on,
        "brain_off": not brain_on,
        "emergency_legacy": emergency,
        "emergency_legacy_default": False,
        "rollback_required_when_brain_off": True,
        "rollback_tag": "rollback/pre-brain-2026-09-11",
        "rollback_sha": "0f23bcf1d35886acec5dbf53eb1af2faf2734757",
        "luna_terra_restored": False,
        "safe_to_leave_brain_off_without_rollback": False,
        "flag_off_stop_reason": (
            "emergency_legacy_unavailable" if emergency else "engine_removed"
        ),
        "note": (
            "Brain OFF does not restore Luna/Terra on this branch. "
            "Redeploy the rollback tag to restore pre-Brain AI."
        ),
    }


def flags_snapshot() -> dict[str, Any]:
    cutover = assert_safe_brain_cutover()
    try:
        from services.customer_ai.tenant_gate import gate_snapshot

        gates = gate_snapshot()
    except Exception:
        gates = {}
    return {
        "customer_brain_enabled": customer_brain_enabled(),
        "emergency_legacy_reply_enabled": emergency_legacy_reply_enabled(),
        "voyage_configured": voyage_configured(),
        "customer_engine": "brain" if customer_brain_enabled() else "removed",
        "cutover": cutover,
        **gates,
    }
