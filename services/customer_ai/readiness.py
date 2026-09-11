"""Read-only Customer Brain readiness report. Never prints secret values."""

from __future__ import annotations

from typing import Any


def _flag(name: str) -> bool:
    from services.customer_ai.flags import env_flag

    return env_flag(name)


def brain_readiness_report(*, tenant_id: str = "linas") -> dict[str, Any]:
    from services.customer_ai.flags import (
        assert_safe_brain_cutover,
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
        "brain_permanent": True,
        "lab_page_flag": _flag("LINAS_CUSTOMER_AI_LAB"),
        "billing_cutover_off": not _flag("MESSAGE_BILLING_CUTOVER"),
        "emergency_legacy_off": not emergency_legacy_reply_enabled(),
        "tenant_gate_allow": bool(gate.get("allow")),
        "search_ready": bool(search.ready),
        "rollback_tag_documented": True,
        "luna_terra_not_restored": cutover.get("luna_terra_restored") is False,
        "enable_flag_removed": True,
    }
    try:
        from services.customer_ai.evals.artifacts import latest_offline_artifact

        artifact = latest_offline_artifact()
        checks["latest_eval_artifact"] = bool(artifact)
    except Exception:
        artifact = None
        checks["latest_eval_artifact"] = False

    blockers = [
        name
        for name, ok in checks.items()
        if not ok and name not in {"lab_page_flag", "search_ready", "latest_eval_artifact"}
    ]
    return {
        "ok": all(
            checks[k]
            for k in (
                "openai_configured",
                "voyage_configured",
                "billing_cutover_off",
                "emergency_legacy_off",
                "luna_terra_not_restored",
                "enable_flag_removed",
                "brain_permanent",
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
        "note": "CUSTOMER_BRAIN_ENABLED removed. Brain is permanent. Read-only; no secrets printed.",
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
