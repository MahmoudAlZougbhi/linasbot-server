"""Owner Copilot tools for self-diagnosis TRACE + corrections."""

from __future__ import annotations

from typing import Any

from modules.api_security import resolve_permissions
from services.owner_ai_tools_base import ToolResult


def _require(role: str, permission: str) -> None:
    if not resolve_permissions(role, None).get(permission):
        raise PermissionError(f"Missing permission: {permission}")


async def tool_get_recent_customer_interactions(
    *,
    tenant_id: str,
    role: str,
    limit: int = 20,
) -> ToolResult:
    _require(role, "liveChat")
    from services.customer_response_trace import get_recent_customer_interactions

    items = get_recent_customer_interactions(tenant_id=tenant_id, limit=max(1, min(int(limit or 20), 50)))
    compact = [
        {
            "trace_id": i.get("trace_id"),
            "channel": i.get("channel"),
            "conversation_id": i.get("conversation_id"),
            "customer_message": i.get("customer_message"),
            "ai_response": (str(i.get("ai_response") or "")[:240] or None),
            "timestamp_iso": i.get("timestamp_iso") or i.get("timestamp"),
            "source": i.get("source"),
            "faq_match": i.get("faq_match"),
        }
        for i in items
    ]
    return ToolResult(
        ok=True,
        name="get_recent_customer_interactions",
        data={"interactions": compact, "count": len(compact)},
    )


async def tool_get_interaction_trace(
    *,
    tenant_id: str,
    role: str,
    trace_id: str,
) -> ToolResult:
    _require(role, "liveChat")
    from services.customer_response_trace import get_interaction_trace
    from services.owner_ai_diagnosis import diagnose_interaction

    if not (trace_id or "").strip():
        return ToolResult(ok=False, name="get_interaction_trace", data={}, error="trace_id required")
    trace = get_interaction_trace(tenant_id=tenant_id, trace_id=trace_id.strip())
    if not trace:
        return ToolResult(ok=False, name="get_interaction_trace", data={}, error="Trace not found")
    diagnosis = diagnose_interaction(tenant_id=tenant_id, trace_id=trace_id.strip())
    return ToolResult(
        ok=True,
        name="get_interaction_trace",
        data={"trace": trace, "diagnosis": diagnosis},
    )


async def tool_propose_diagnosis_fix(
    *,
    tenant_id: str,
    role: str,
    user_id: str,
    trace_id: str,
    correction: dict[str, Any] | None = None,
) -> ToolResult:
    _require(role, "contentManagers")
    from services.owner_ai_diagnosis import propose_diagnosis_fix

    data = propose_diagnosis_fix(
        tenant_id=tenant_id,
        user_id=user_id,
        trace_id=trace_id,
        correction_override=correction,
    )
    return ToolResult(
        ok=True,
        name="propose_diagnosis_fix",
        data=data,
        requires_confirmation=True,
        confirmation_token=str(data.get("confirmation_token")),
        error="Confirmation required before applying diagnosis fix",
    )


async def tool_approve_diagnosis_fix(
    *,
    tenant_id: str,
    role: str,
    user_id: str,
    proposal_id: str,
    confirmed: bool,
) -> ToolResult:
    _require(role, "contentManagers")
    if not confirmed:
        return ToolResult(
            ok=True,
            name="approve_diagnosis_fix",
            data={"proposal_id": proposal_id, "action": "approve_diagnosis_fix"},
            requires_confirmation=True,
            confirmation_token=f"approve_diagnosis_fix:{proposal_id}",
            error="Confirmation required",
        )
    from services.owner_ai_diagnosis import approve_diagnosis_fix

    data = await approve_diagnosis_fix(
        tenant_id=tenant_id,
        user_id=user_id,
        proposal_id=proposal_id,
    )
    return ToolResult(ok=True, name="approve_diagnosis_fix", data=data)
