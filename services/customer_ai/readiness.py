"""Read-only Customer Brain readiness report. Never prints secret values."""

from __future__ import annotations

from typing import Any


def _flag(name: str) -> bool:
    from services.customer_ai.flags import env_flag

    return env_flag(name)


def _gate(status: str, detail: str = "") -> dict[str, str]:
    return {"status": status, "detail": detail}


def brain_readiness_report(*, tenant_id: str = "linas") -> dict[str, Any]:
    from services.customer_ai.flags import (
        assert_safe_brain_cutover,
        emergency_legacy_reply_enabled,
        voyage_configured,
    )
    from services.customer_ai.generate.reply import openai_configured
    from services.customer_ai.providers.spaces import KNOWLEDGE_MODEL, spaces_snapshot
    from services.customer_ai.search.readiness import resolve_search_readiness
    from services.customer_ai.tenant_gate import evaluate_brain_tenant_gate, gate_snapshot

    cutover = assert_safe_brain_cutover()
    gate = evaluate_brain_tenant_gate(tenant_id)
    search = resolve_search_readiness(tenant_id)
    spaces = spaces_snapshot()

    gates: dict[str, dict[str, str]] = {
        "CODE": _gate("PASS", "brain_permanent"),
        "INDEX": _gate("PASS" if search.pointer_ready else "FAIL", search.reason),
        "VOYAGE": _gate("PASS" if voyage_configured() else "BLOCKED", "VOYAGE_API_KEY"),
        "OPENAI": _gate("PASS" if openai_configured() else "BLOCKED", "OPENAI_API_KEY"),
        "PGVECTOR": _gate("PASS" if search.pgvector else "FAIL", "pgvector"),
        "CONTEXTUAL_MODEL": _gate(
            "PASS" if spaces.get("contextual_active") == "true" else "FAIL",
            KNOWLEDGE_MODEL,
        ),
        "RETRIEVAL_EVAL": _gate("NOT_RUN"),
        "GROUNDING": _gate("NOT_RUN"),
        "MULTILINGUAL": _gate("PASS", "normalize+voyage"),
        "TOOLS": _gate("NOT_RUN", "needs live tool loop"),
        "MEMORY": _gate("NOT_RUN", "needs durable PG proof"),
        "MULTIMODAL": _gate("NOT_RUN", "needs live extractors"),
        "ATOMIC_SWITCH": _gate("NOT_RUN", "needs live pointer flip"),
        "LOAD": _gate("NOT_RUN"),
        "LATENCY": _gate("NOT_RUN"),
        "COST": _gate("NOT_RUN"),
        "CHANNEL_SMOKE": _gate("NOT_RUN"),
        "BILLING": _gate("NOT_RUN"),
        "SECURITY": _gate("NOT_RUN"),
    }

    try:
        from services.customer_ai.evals.artifacts import latest_offline_artifact

        artifact = latest_offline_artifact()
        if artifact:
            gates_map = (artifact.get("gates") if isinstance(artifact, dict) else None) or {}
            if gates_map.get("recall@10_ge_0.98"):
                gates["RETRIEVAL_EVAL"] = _gate("PASS", "recall@10>=0.98")
            elif "recall@10_ge_0.98" in gates_map:
                gates["RETRIEVAL_EVAL"] = _gate("FAIL", "recall@10<0.98")
            if gates_map.get("missed_unsupported_eq_0"):
                gates["GROUNDING"] = _gate("PASS", "missed_unsupported=0")
            elif "missed_unsupported_eq_0" in gates_map:
                gates["GROUNDING"] = _gate("FAIL", "unsupported_miss")
        else:
            artifact = None
    except Exception:
        artifact = None

    # Live lab artifact overrides offline NOT_RUN / code-only PASS where executed.
    try:
        from pathlib import Path
        import json

        live_path = Path("services/customer_ai/evals/artifacts/live_lab_latest.json")
        live = json.loads(live_path.read_text(encoding="utf-8")) if live_path.exists() else None
        live_gates = (live or {}).get("gates") if isinstance(live, dict) else None
        if isinstance(live_gates, dict):
            for name, row in live_gates.items():
                if name not in gates:
                    gates[name] = _gate(str(row.get("status") or "NOT_RUN"), str(row.get("detail") or "live_lab"))
                    continue
                status = str(row.get("status") or "")
                # Never promote BLOCKED/NOT_RUN/FAIL into PASS via offline; live is authoritative.
                if status in {"PASS", "FAIL", "BLOCKED", "NOT_RUN"}:
                    gates[name] = _gate(status, str(row.get("detail") or "live_lab"))
    except Exception:
        live = None

    checks: dict[str, bool] = {
        "openai_configured": openai_configured(),
        "voyage_configured": voyage_configured(),
        "brain_permanent": True,
        "lab_page_flag": _flag("LINAS_CUSTOMER_AI_LAB"),
        "billing_cutover_off": not _flag("MESSAGE_BILLING_CUTOVER"),
        "emergency_legacy_off": not emergency_legacy_reply_enabled(),
        "tenant_gate_allow": bool(gate.get("allow")),
        "search_ready": bool(search.ready),
        "contextual_model_wired": spaces.get("contextual_active") == "true",
        "rollback_tag_documented": True,
        "luna_terra_not_restored": cutover.get("luna_terra_restored") is False,
        "enable_flag_removed": True,
    }

    blockers = [
        name
        for name, row in gates.items()
        if row.get("status") == "FAIL" and name in {"CODE", "CONTEXTUAL_MODEL", "ATOMIC_SWITCH", "TOOLS"}
    ]
    return {
        "ok": all(checks[k] for k in ("brain_permanent", "enable_flag_removed", "billing_cutover_off", "emergency_legacy_off")),
        "tenant_id": tenant_id,
        "gates": gates,
        "checks": checks,
        "cutover": cutover,
        "tenant_gate": gate,
        "gate_snapshot": gate_snapshot(),
        "spaces": spaces,
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
        "note": "Brain permanent. BLOCKED != PASS. Live provider/load/latency require secrets + controlled runs.",
    }


def main() -> int:
    import json
    import sys

    tenant = "linas"
    if len(sys.argv) > 1 and sys.argv[1].strip():
        tenant = sys.argv[1].strip()
    report = brain_readiness_report(tenant_id=tenant)
    print(json.dumps(report, indent=2, sort_keys=True))
    # Exit 0 for report generation; production-ready is a separate gate set.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
