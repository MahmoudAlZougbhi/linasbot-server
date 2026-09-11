"""Assemble Owner-facing message flow cards from outbox + costs + logs."""

from __future__ import annotations

from typing import Any

from services.customer_ai.outbox import list_recent, outbox_id_for
from services.customer_ai.stage_timeline import public_flow_from_extra
from services.membership.expense_journal import list_events
from services.membership.message_ledger import list_reservations
from services.membership.pending_settlement import get_pending


def _cost_for_operation(tenant_id: str, operation_id: str) -> dict[str, Any]:
    events = [
        item
        for item in list_events(tenant_id=tenant_id)
        if str(item.operation_id or "") == operation_id or str(item.event_id or "").endswith(f":{operation_id}")
    ]
    pending = sum(1 for item in events if item.status in {"pending", "unpriced"})
    known = sum((item.amount_usd or 0) for item in events if item.status == "known" and item.amount_usd is not None)
    return {
        "pending_events": pending,
        "known_usd": str(known),
        "events": [
            {
                "category": item.category,
                "feature": item.feature,
                "provider": item.provider,
                "model": item.model,
                "status": item.status,
                "amount_usd": None if item.amount_usd is None else str(item.amount_usd),
            }
            for item in events
        ],
    }


def _interaction_row(tenant_id: str, operation_id: str) -> dict[str, Any] | None:
    try:
        from services.interaction_flow_logger import get_recent_flows

        rows = get_recent_flows(tenant_id=tenant_id, limit=200)
    except Exception:
        return None
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        mid = str(row.get("message_id") or row.get("trace_id") or "")
        if mid == operation_id:
            return row
    return None


def list_message_flows(*, tenant_id: str = "", limit: int = 50) -> list[dict[str, Any]]:
    items = list_recent(tenant_id=tenant_id or "", limit=max(1, min(limit, 200)))
    rows: list[dict[str, Any]] = []
    for item in items:
        extra = dict(item.extra or {})
        cost = _cost_for_operation(item.tenant_id, item.operation_id)
        reply_texts = []
        envelope = item.envelope if isinstance(item.envelope, dict) else {}
        for message in envelope.get("messages") or []:
            if isinstance(message, dict) and str(message.get("text") or "").strip():
                reply_texts.append(str(message.get("text") or "").strip()[:500])
        rows.append(
            {
                "tenant_id": item.tenant_id,
                "operation_id": item.operation_id,
                "outbox_id": item.outbox_id,
                "channel": str(extra.get("channel") or ""),
                "conversation_id": str(extra.get("conversation_id") or ""),
                "surface": str(extra.get("surface") or ""),
                "state": item.state,
                "updated_at": item.updated_at,
                "inbound_preview": str(extra.get("inbound_preview") or "")[:280],
                "reply_preview": reply_texts[0] if reply_texts else "",
                "phase": str(extra.get("phase") or ""),
                "message_units": extra.get("message_units"),
                "response_class": extra.get("response_class"),
                "pending_cost_events": cost["pending_events"],
                "known_usd": cost["known_usd"],
                "stage_count": len(extra.get("stage_timeline") or []),
            }
        )
    return rows


def get_message_flow(*, tenant_id: str, operation_id: str) -> dict[str, Any] | None:
    tid = (tenant_id or "").strip()
    op = (operation_id or "").strip()
    if not tid or not op:
        return None
    items = {item.outbox_id: item for item in list_recent(tenant_id=tid, limit=200)}
    item = items.get(outbox_id_for(tid, op))
    if item is None:
        for candidate in items.values():
            if candidate.operation_id == op:
                item = candidate
                break
    if item is None:
        return None
    extra = dict(item.extra or {})
    cost = _cost_for_operation(tid, op)
    settlement = get_pending(tid, op, op)
    reservations = [row for row in list_reservations(tid) if str(getattr(row, "operation_id", "")) == op]
    interaction = _interaction_row(tid, op)
    flow = public_flow_from_extra(extra)
    if cost["pending_events"] or cost["known_usd"] not in {"0", "0.0"}:
        flow.append(
            {
                "stage": "cost",
                "title": "Cost recorded for this turn",
                "at": item.updated_at,
                "detail": {
                    "cost_pending_events": cost["pending_events"],
                    "known_usd": cost["known_usd"],
                },
            }
        )
    envelope = item.envelope if isinstance(item.envelope, dict) else {}
    return {
        "tenant_id": tid,
        "operation_id": op,
        "channel": str(extra.get("channel") or ""),
        "conversation_id": str(extra.get("conversation_id") or ""),
        "surface": str(extra.get("surface") or ""),
        "inbound_preview": str(extra.get("inbound_preview") or ""),
        "state": item.state,
        "provider_message_id": item.provider_message_id,
        "updated_at": item.updated_at,
        "decision": envelope.get("decision"),
        "reply_messages": [
            {"destination": m.get("destination"), "text": m.get("text")}
            for m in (envelope.get("messages") or [])
            if isinstance(m, dict)
        ],
        "used_evidence_ids": envelope.get("used_evidence_ids") or extra.get("used_evidence_ids") or [],
        "evidence_sent_to_ai": extra.get("evidence_preview") or [],
        "flow": flow,
        "billing": {
            "message_units": extra.get("message_units"),
            "response_class": extra.get("response_class"),
            "billing_policy": extra.get("billing_policy"),
            "reservation_status": getattr(reservations[0], "status", None) if reservations else None,
            "settlement_state": getattr(settlement, "state", None) if settlement else None,
        },
        "cost": cost,
        "interaction": {
            "user_message": (interaction or {}).get("user_message"),
            "bot_to_user": (interaction or {}).get("bot_to_user"),
            "source": (interaction or {}).get("source"),
            "outcome": (interaction or {}).get("outcome"),
        }
        if interaction
        else None,
        "note": (
            "Stages are customer-readable. Full AI prompts are not shown. "
            "Known USD stays 0 until invoice finalization; pending events still attribute spend to this tenant."
        ),
    }
