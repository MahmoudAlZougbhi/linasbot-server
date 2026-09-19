"""Canonical live meter is the message ledger. Credit ledger is historical/audit only."""

from __future__ import annotations

from typing import Any

ACTIVATION_FLAG_NAMES = (
    "MESSAGE_BILLING_ENABLED",
    "MESSAGE_BILLING_CUTOVER",
    "FREE_PLAN_ENFORCEMENT_ENABLED",
)


def activation_flags_report(values: dict[str, str] | None = None) -> dict[str, Any]:
    """Commercial activation env flags. Live metering does not wait on these."""
    _ = values
    flags = [{"key": key, "set": False, "enabled": False} for key in ACTIVATION_FLAG_NAMES]
    return {"ok": True, "enabled": [], "flags": flags}


def message_billing_enabled() -> bool:
    """Canonical live meter is the message ledger. Always on."""
    return True


def message_billing_cutover() -> bool:
    """Store checkout sale_ready still waits on catalog publish. Temporary cutover."""
    return False


def free_enforcement_enabled() -> bool:
    return False
