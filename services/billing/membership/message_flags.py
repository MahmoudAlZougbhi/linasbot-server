"""Message billing is not a live meter. Subscription charges credits only."""

from __future__ import annotations

from typing import Any

# Kept as names so old env/docs/tests can import. Values are always off.
ACTIVATION_FLAG_NAMES = (
    "MESSAGE_BILLING_ENABLED",
    "MESSAGE_BILLING_CUTOVER",
    "FREE_PLAN_ENFORCEMENT_ENABLED",
)


def activation_flags_report(values: dict[str, str] | None = None) -> dict[str, Any]:
    _ = values
    flags = [{"key": key, "set": False, "enabled": False} for key in ACTIVATION_FLAG_NAMES]
    return {"ok": True, "enabled": [], "flags": flags}


def message_billing_enabled() -> bool:
    """Always false. Live AI and IAP use the credit ledger."""
    return False


def message_billing_cutover() -> bool:
    """Always false. Draft message catalog is not checkout SoT."""
    return False


def free_enforcement_enabled() -> bool:
    return False
