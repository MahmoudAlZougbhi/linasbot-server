"""Tera resource_actions: validate published AI Setup resources. Sending is Phase 5."""

from __future__ import annotations

from typing import Any

from services.cm.setup_resources import resolve_published_resource

ALLOWED_ACTION = "send_resource"


def parse_resource_actions(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw[:8]:
        if not isinstance(item, dict):
            continue
        action = str(item.get("action") or "").strip()
        ref = str(item.get("resource_ref") or item.get("resource_id") or "").strip()
        if action != ALLOWED_ACTION or not ref or ref in seen:
            continue
        seen.add(ref)
        out.append({"action": ALLOWED_ACTION, "resource_ref": ref})
    return out


def resolve_resource_actions(
    *,
    tenant_id: str,
    actions: list[dict[str, Any]],
    allowed_source_ids: list[str] | None = None,
    channel_capabilities: dict[str, Any] | None = None,
    idempotency_key: str = "",
) -> dict[str, Any]:
    caps = dict(channel_capabilities or {})
    max_channel = int(caps.get("max_media_items") or 0)
    if not actions:
        return {"ok": True, "items": [], "ai_charged": False, "idempotency_key": idempotency_key}

    delivered: list[dict[str, Any]] = []
    for action in actions:
        ref = str(action.get("resource_ref") or "").strip()
        hit = resolve_published_resource(
            tenant_id=tenant_id,
            resource_ref=ref,
            allowed_source_ids=list(allowed_source_ids or []),
        )
        if not hit.get("ok"):
            return {
                "ok": False,
                "error": str(hit.get("error") or "resource_not_found"),
                "resource_ref": ref,
                "items": delivered,
                "ai_charged": False,
                "claimed_sent": False,
            }
        record = dict(hit.get("resource") or {})
        kind = str(record.get("resource_type") or "file")
        if kind != "link" and max_channel <= 0:
            return {
                "ok": False,
                "error": "channel_cannot_send_media",
                "resource_ref": ref,
                "items": delivered,
                "ai_charged": False,
                "claimed_sent": False,
                "owner_diagnostic": "Channel cannot send AI Setup media for this surface.",
            }
        delivered.append(
            {
                "resource_ref": ref,
                "resource_type": kind,
                "source_item_id": str(record.get("source_item_id") or ""),
                "title": str(record.get("title") or ""),
                "status": str(record.get("status") or "active"),
            }
        )
    return {
        "ok": True,
        "items": delivered,
        "ai_charged": False,
        "idempotency_key": idempotency_key,
        "delivery_result": "resolved_pending_channel_send",
        "claimed_sent": False,
        "extra_tera_call": False,
    }


def plan_resources_for_turn(
    *,
    tenant_id: str,
    answer: Any,
    channel_metadata: dict[str, Any] | None,
    meter: Any | None = None,
    idempotency_key: str = "",
    allowed_source_ids: list[str] | None = None,
) -> dict[str, Any]:
    from services.customer_reply_v2.flags import customer_ai_v10_runtime_enabled
    from services.customer_reply_v2.invocation_meter import InvocationRecord

    if not customer_ai_v10_runtime_enabled():
        return {}
    raw = getattr(answer, "resource_actions", None)
    if raw is None:
        raw = (getattr(answer, "raw_structured", None) or {}).get("resource_actions")
    actions = parse_resource_actions(raw)
    if not actions:
        return {"resource_actions": [], "resource_delivery": {"ok": True, "items": [], "ai_charged": False}}
    caps = dict((channel_metadata or {}).get("channel_capabilities") or {})
    plan = resolve_resource_actions(
        tenant_id=tenant_id,
        actions=actions,
        allowed_source_ids=allowed_source_ids,
        channel_capabilities=caps,
        idempotency_key=idempotency_key,
    )
    if meter is not None:
        meter.record(
            InvocationRecord(
                operation="resource_delivery",
                is_ai=False,
                success=bool(plan.get("ok")),
                failure_stage=None if plan.get("ok") else str(plan.get("error") or "resource_delivery"),
            )
        )
    return {"resource_actions": actions, "resource_delivery": plan}
