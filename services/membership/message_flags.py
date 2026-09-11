"""Independent default-off controls for message billing. Not Customer Brain."""

from __future__ import annotations

import os
from typing import Any

# Commerce/billing cutover only. LINAS_CUSTOMER_AI_LAB is Owner Lab UI and is
# allowed on during controlled Customer Brain production validation.
ACTIVATION_FLAG_NAMES = (
    "MESSAGE_BILLING_ENABLED",
    "MESSAGE_BILLING_CUTOVER",
    "FREE_PLAN_ENFORCEMENT_ENABLED",
)


def _flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _truthy(raw: str) -> bool:
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def activation_flags_report(values: dict[str, str] | None = None) -> dict[str, Any]:
    src = values if values is not None else {key: os.getenv(key, "") for key in ACTIVATION_FLAG_NAMES}
    enabled: list[str] = []
    flags: list[dict[str, Any]] = []
    for key in ACTIVATION_FLAG_NAMES:
        raw = str(src.get(key) or "").strip()
        on = _truthy(raw)
        flags.append({"key": key, "set": bool(raw), "enabled": on})
        if on:
            enabled.append(key)
    return {"ok": not enabled, "enabled": enabled, "flags": flags}


def message_billing_enabled() -> bool:
    """When false, Customer AI still uses the live credit gate."""
    return _flag("MESSAGE_BILLING_ENABLED")


def message_billing_cutover() -> bool:
    """When false, checkout and grants stay on the live credit catalog."""
    return _flag("MESSAGE_BILLING_CUTOVER")


def free_enforcement_enabled() -> bool:
    """Free slot/content caps. Off until owner confirms section-2 values."""
    return _flag("FREE_PLAN_ENFORCEMENT_ENABLED")
