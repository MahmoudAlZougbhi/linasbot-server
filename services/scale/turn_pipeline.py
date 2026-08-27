"""Pipeline stages for one inbound message. Maps lifecycle + delivery ledger.

Canonical stages (recovery resume points):

received → persisted → queued → processing → ai_started → ai_generated
→ delivery_pending → delivery_started → sent → completed
"""

from __future__ import annotations

from typing import Any

STAGES = (
    "received",
    "persisted",
    "queued",
    "processing",
    "ai_started",
    "luna_done",
    "tera_done",
    "ai_generated",
    "delivery_pending",
    "delivery_started",
    "sent",
    "completed",
    "failed",
    "unknown_delivery",
)

_LIFECYCLE_TO_STAGE = {
    "RECEIVED_NO_CHARGE": "received",
    "AI_PENDING": "queued",
    "AI_PROCESSING": "ai_started",
    "AI_GENERATED": "ai_generated",
    "REPLY_PERSISTED": "delivery_pending",
    "CREDIT_CAPTURED_ONCE": "delivery_pending",
    "OUTBOUND_PENDING": "delivery_started",
    "OUTBOUND_RETRY": "delivery_pending",
    "DELIVERY_RETRY_WITHOUT_REGENERATION": "delivery_pending",
    "DELIVERED": "completed",
    "NEEDS_OWNER_ACTION": "unknown_delivery",
    "PERMANENT_DELIVERY_BLOCK": "failed",
    "NO_FINAL_CHARGE": "failed",
    "AI_RETRY_REQUIRED": "failed",
}


def pipeline_stage(*, lifecycle_state: str = "", delivery_state: str = "", inbound_state: str = "") -> str:
    delivery = (delivery_state or "").strip().lower()
    if delivery == "sent":
        return "sent" if (lifecycle_state or "") != "DELIVERED" else "completed"
    if delivery in {"unknown", "started"}:
        return "unknown_delivery" if delivery == "unknown" else "delivery_started"
    mapped = _LIFECYCLE_TO_STAGE.get(str(lifecycle_state or "").strip())
    if mapped:
        return mapped
    inbound = (inbound_state or "").strip().lower()
    if inbound in {"accepted", "queued", "processing", "completed", "failed", "dead_letter"}:
        return {"accepted": "persisted", "dead_letter": "failed"}.get(inbound, inbound)
    return "received"


def set_pipeline_stage(logical_reply_id: str, stage: str) -> None:
    lid = (logical_reply_id or "").strip()
    if not lid or stage not in STAGES:
        return
    from services.scale.turn_store import load_turn, save_turn

    data: dict[str, Any] = load_turn(lid) or {"logical_reply_id": lid}
    data["pipeline_stage"] = stage
    save_turn(data)


def get_pipeline_stage(logical_reply_id: str) -> str:
    from services.scale.turn_store import load_turn

    data = load_turn((logical_reply_id or "").strip()) or {}
    return str(data.get("pipeline_stage") or pipeline_stage(lifecycle_state=str(data.get("state") or "")))
