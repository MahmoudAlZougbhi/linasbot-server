"""Channel/plan capability gates only — Brain is permanent (no experimental allowlist)."""

from __future__ import annotations

from typing import Any


def evaluate_brain_tenant_gate(tenant_id: str) -> dict[str, Any]:
    """Allow any non-empty tenant. Plan/channel entitlements are enforced elsewhere."""
    tid = (tenant_id or "").strip()
    if not tid:
        return {"allow": False, "reason": "missing_tenant", "path": "missing_tenant"}
    return {"allow": True, "reason": "ok", "path": "plan_channel"}


def gate_snapshot() -> dict[str, Any]:
    return {
        "brain_permanent": True,
        "experimental_allowlist_removed": True,
        "lab_runtime_gate_removed": True,
        "note": "Lab UI may still use LINAS_CUSTOMER_AI_LAB for the isolated Owner Lab page only.",
    }
