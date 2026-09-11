"""Hard tenant gates before Customer Brain serves real customers."""

from __future__ import annotations

import os
from typing import Any

from services.customer_ai.flags import env_flag

ALLOWLIST_ENV = "CUSTOMER_BRAIN_TENANT_ALLOWLIST"
LAB_ENV = "LINAS_CUSTOMER_AI_LAB"

# Documented Linas Laser production tenant (services/cm/constants.DEFAULT_TENANT_ID).
_DEFAULT_ALLOWLIST = frozenset({"linas"})


def brain_tenant_allowlist() -> frozenset[str]:
    raw = (os.getenv(ALLOWLIST_ENV) or "").strip()
    if not raw:
        return _DEFAULT_ALLOWLIST
    return frozenset(part.strip() for part in raw.split(",") if part.strip())


def _lab_tenant(tenant_id: str) -> bool:
    tid = (tenant_id or "").strip().lower()
    return tid == "lab" or tid.startswith("lab_")


def lab_flag_enabled() -> bool:
    return env_flag(LAB_ENV)


def evaluate_brain_tenant_gate(tenant_id: str) -> dict[str, Any]:
    """Allowlist / lab / activation testing_ready. Fail closed otherwise."""
    tid = (tenant_id or "").strip()
    if not tid:
        return {"allow": False, "reason": "brain_gates_incomplete", "path": "missing_tenant"}
    if _lab_tenant(tid):
        if lab_flag_enabled():
            return {"allow": True, "reason": "ok", "path": "lab"}
        return {"allow": False, "reason": "brain_gates_incomplete", "path": "lab_flag_off"}
    if tid in brain_tenant_allowlist():
        return {"allow": True, "reason": "ok", "path": "allowlist"}
    try:
        from services.membership.activation_readiness import activation_readiness

        report = activation_readiness()
    except Exception:
        return {"allow": False, "reason": "brain_gates_incomplete", "path": "readiness_error"}
    if bool(report.get("testing_ready")):
        return {"allow": True, "reason": "ok", "path": "testing_ready"}
    return {
        "allow": False,
        "reason": "brain_gates_incomplete",
        "path": "testing_ready_missing",
        "testing_blockers": list(report.get("testing_blockers") or []),
    }


def gate_snapshot() -> dict[str, Any]:
    return {
        "tenant_allowlist": sorted(brain_tenant_allowlist()),
        "lab_tenants_allowed": lab_flag_enabled(),
        "default_allowlist": sorted(_DEFAULT_ALLOWLIST),
    }
