"""Phase 8 cutover rehearsal helpers + readiness gate (plan §14).

Rehearsal runs a full publish (validate → version write → index build → pointer flip) against
an ISOLATED rehearsal tenant id derived from the real tenant, so it never touches the real
tenant's draft/published state — the real draft is only ever READ, then deep-copied.

The readiness gate aggregates validation + SoT-audit signals into a single, read-only report.
It never flips ``CM_RUNTIME_MODE`` or ``CM_PUBLISH_ENABLED`` itself — those remain explicit,
human-approved environment changes (server/infra config changes require approval first).
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from services.cm.constants import CM_SECTIONS, DEFAULT_TENANT_ID
from services.cm.publish import PublishBlockedError, publish_draft
from services.cm.sot_audit import audit_sot_sources
from services.cm.storage import get_draft, put_draft
from services.cm.validation import validate_cm

REHEARSAL_TENANT_SUFFIX = "__cutover_rehearsal"


def rehearsal_tenant_id(tenant_id: str | None = None) -> str:
    base = (tenant_id or DEFAULT_TENANT_ID).strip() or DEFAULT_TENANT_ID
    return f"{base}{REHEARSAL_TENANT_SUFFIX}"


def seed_rehearsal_tenant_from_draft(*, tenant_id: str | None = None) -> str:
    """Deep-copy the real tenant's CURRENT draft into an isolated rehearsal tenant's draft.

    Idempotent: safe to call repeatedly (each call re-syncs the rehearsal draft to the latest
    real draft). The real tenant's draft is only ever read here, never written.
    """
    source_tid = (tenant_id or DEFAULT_TENANT_ID).strip() or DEFAULT_TENANT_ID
    target_tid = rehearsal_tenant_id(source_tid)

    for section in CM_SECTIONS:
        source_env = get_draft(section, tenant_id=source_tid, create_default=True)
        target_current = get_draft(section, tenant_id=target_tid, create_default=True)
        put_draft(
            section,
            payload=copy.deepcopy(source_env.payload),
            if_match=target_current.etag,
            tenant_id=target_tid,
            updated_by="cutover_rehearsal",
        )
    return target_tid


async def run_publish_rehearsal(
    *,
    tenant_id: str | None = None,
    published_by: str = "cutover_rehearsal",
) -> dict[str, Any]:
    """Seed an isolated rehearsal tenant from the real draft, then run a full publish on it.

    Returns the publish result (or the validation-blocked error). NEVER touches the real
    tenant's published pointer, and never requires ``CM_PUBLISH_ENABLED`` for the real tenant —
    callers still need publish enabled for this rehearsal call itself (same publish machinery),
    but no customer-facing runtime ever reads the rehearsal tenant's pointer.
    """
    rehearsal_tid = seed_rehearsal_tenant_from_draft(tenant_id=tenant_id)
    try:
        result = await publish_draft(tenant_id=rehearsal_tid, published_by=published_by)
    except PublishBlockedError as exc:
        return {
            "ok": False,
            "rehearsal_tenant_id": rehearsal_tid,
            "error": exc.message,
            "errors": exc.errors,
        }
    return {
        "ok": True,
        "rehearsal_tenant_id": rehearsal_tid,
        "content_version_id": result.content_version_id,
        "index_version_id": result.index_version_id,
    }


@dataclass
class ReadinessGateResult:
    ready: bool
    checks: dict[str, Any]


def evaluate_cutover_readiness(*, tenant_id: str | None = None) -> ReadinessGateResult:
    """Aggregate, read-only readiness signal for Phase 8 cutover. Never flips any flag.

    ``ready`` only reflects hard blockers (draft validation errors). Ungated legacy SoT
    sources are surfaced as a warning list for human review, not a hard blocker — some legacy
    sources (e.g. booking/CRM flows) are explicitly out of CM's scope for this phase.
    """
    tid = (tenant_id or DEFAULT_TENANT_ID).strip() or DEFAULT_TENANT_ID
    validation = validate_cm(tenant_id=tid)
    audit = audit_sot_sources()

    ungated_sources = [
        source["id"]
        for source in audit["sources"]
        if source["referenced_in"] and not source["fully_gated_by_cm_runtime_mode"]
    ]

    checks: dict[str, Any] = {
        "draft_validation_ok": validation["ok"],
        "draft_validation_error_count": validation["error_count"],
        "draft_validation_errors": validation["errors"],
        "sot_audit": audit,
        "ungated_legacy_sources": ungated_sources,
    }
    return ReadinessGateResult(ready=validation["ok"], checks=checks)
