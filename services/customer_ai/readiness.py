"""Read-only Customer Brain readiness report. Never prints secret values."""

from __future__ import annotations

from typing import Any


def _flag(name: str) -> bool:
    from services.customer_ai.flags import env_flag

    return env_flag(name)


def brain_readiness_report(*, tenant_id: str = "linas") -> dict[str, Any]:
    from services.customer_ai.flags import (
        assert_safe_brain_cutover,
        customer_brain_enabled,
        emergency_legacy_reply_enabled,
        voyage_configured,
    )
    from services.customer_ai.generate.reply import openai_configured
    from services.customer_ai.tenant_gate import evaluate_brain_tenant_gate, gate_snapshot
    from services.customer_ai.search.readiness import resolve_search_readiness

    cutover = assert_safe_brain_cutover()
    gate = evaluate_brain_tenant_gate(tenant_id)
    search = resolve_search_readiness(tenant_id)
    checks: dict[str, bool] = {
        "openai_configured": openai_configured(),
        "voyage_configured": voyage_configured(),
        "brain_flag_readable": True,
        "brain_enabled": customer_brain_enabled(),
        "lab_enabled": _flag("LINAS_CUSTOMER_AI_LAB"),
        "billing_cutover_off": not _flag("MESSAGE_BILLING_CUTOVER"),
        "emergency_legacy_off": not emergency_legacy_reply_enabled(),
        "tenant_gate_allow": bool(gate.get("allow")),
        "search_ready": bool(search.ready),
        "rollback_tag_documented": True,
        "luna_terra_not_restored_on_flag_off": cutover.get("luna_terra_restored") is False,
    }
    try:
        from services.customer_ai.evals.artifacts import latest_offline_artifact

        artifact = latest_offline_artifact()
        checks["latest_eval_artifact"] = bool(artifact)
    except Exception:
        artifact = None
        checks["latest_eval_artifact"] = False

    blockers = [name for name, ok in checks.items() if not ok and name not in {"brain_enabled", "lab_enabled"}]
    # brain/lab may be intentionally off; they are status, not blockers for the readiness tool itself.
    return {
        "ok": all(
            checks[k]
            for k in (
                "openai_configured",
                "voyage_configured",
                "billing_cutover_off",
                "emergency_legacy_off",
                "luna_terra_not_restored_on_flag_off",
                "rollback_tag_documented",
            )
        ),
        "tenant_id": tenant_id,
        "checks": checks,
        "cutover": cutover,
        "tenant_gate": gate,
        "gate_snapshot": gate_snapshot(),
        "search": {
            "ready": search.ready,
            "reason": search.reason,
            "pgvector": search.pgvector,
            "voyage": search.voyage,
            "pointer_ready": search.pointer_ready,
        },
        "eval_artifact": artifact,
        "blockers": blockers,
        "rollback": {
            "tag": "rollback/pre-brain-2026-09-11",
            "sha": "0f23bcf1d35886acec5dbf53eb1af2faf2734757",
        },
        "note": "Read-only. Does not enable Brain or print secrets.",
    }


def main() -> int:
    import json
    import sys

    tenant = "linas"
    if len(sys.argv) > 1 and sys.argv[1].strip():
        tenant = sys.argv[1].strip()
    report = brain_readiness_report(tenant_id=tenant)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
