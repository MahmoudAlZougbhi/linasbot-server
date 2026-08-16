"""Parse and execute Tera draft_actions / request_actions. No text inference."""

from __future__ import annotations

from typing import Any

ALLOWED_ACTIONS = {
    "create_draft",
    "update_fields",
    "add_item",
    "remove_item",
    "replace_item",
    "pause",
    "resume",
    "cancel",
    "submit",
}


def parse_draft_actions(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw[:8]:
        if not isinstance(item, dict):
            continue
        name = str(item.get("action") or "").strip()
        if name not in ALLOWED_ACTIONS:
            continue
        out.append(dict(item))
    return out


def parse_request_actions(raw: Any) -> list[dict[str, Any]]:
    actions = parse_draft_actions(raw)
    return [item for item in actions if item.get("action") == "submit"]


def plan_drafts_for_turn(
    *,
    tenant_id: str,
    customer_id: str,
    conversation_id: str = "",
    channel: str = "",
    answer: Any,
    meter: Any | None = None,
    idempotency_key: str = "",
    is_public: bool = False,
) -> dict[str, Any]:
    from services.customer_reply_v2.flags import customer_ai_v10_runtime_enabled
    from services.requests.capture import is_public_comment_channel

    if not customer_ai_v10_runtime_enabled():
        return {}
    structured = getattr(answer, "raw_structured", None) or {}
    actions = parse_draft_actions(getattr(answer, "draft_actions", None) or structured.get("draft_actions"))
    actions.extend(parse_request_actions(getattr(answer, "request_actions", None) or structured.get("request_actions")))
    if not actions:
        return {"draft_actions": [], "draft_result": {"ok": True, "results": [], "is_ai": False}}
    if is_public or is_public_comment_channel(channel):
        result = {
            "ok": False,
            "error": "public_comment_refused",
            "results": [],
            "is_ai": False,
            "owner_diagnostic": "Request drafts cannot collect PII on public comments.",
        }
        _meter(meter, success=False, stage="public_comment_refused")
        return {"draft_actions": actions, "draft_result": result}

    from db.session import WhatsAppDatabaseUnavailable, database_url, whatsapp_session
    from services.request_drafts.engine import apply_draft_actions

    if not database_url() or not customer_id:
        result = {"ok": False, "error": "draft_context_unavailable", "results": [], "is_ai": False}
        _meter(meter, success=False, stage="draft_context_unavailable")
        return {"draft_actions": actions, "draft_result": result}
    try:
        with whatsapp_session(require=True) as session:
            result = apply_draft_actions(
                session,
                tenant_id=tenant_id,
                customer_id=customer_id,
                conversation_id=conversation_id,
                actions=[{**item, "idempotency_key": idempotency_key} for item in actions],
            )
    except WhatsAppDatabaseUnavailable:
        result = {"ok": False, "error": "db_unavailable", "results": [], "is_ai": False}
    _meter(
        meter, success=bool(result.get("ok")), stage=None if result.get("ok") else str(result.get("error") or "draft")
    )
    return {"draft_actions": actions, "draft_result": result}


def _meter(meter: Any | None, *, success: bool, stage: str | None) -> None:
    if meter is None:
        return
    from services.customer_reply_v2.invocation_meter import InvocationRecord

    meter.record(
        InvocationRecord(
            operation="draft_storage",
            provider="none",
            is_ai=False,
            success=success,
            failure_stage=stage,
        )
    )
