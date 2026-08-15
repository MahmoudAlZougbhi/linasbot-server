"""Runtime hooks wiring lifecycle + credit gate into text_handlers respond pipeline."""

from __future__ import annotations

from typing import Any

from services.ai_reply_credit_gate import (
    capture_after_reply_persisted,
    release_on_ai_failure,
    reserve_before_ai,
)
from services.ai_reply_delivery import record_delivery_outcome
from services.ai_reply_lifecycle import (
    begin_turn,
    find_pending_delivery_turn,
    get_turn,
    persist_generated_reply,
)

_TURN_RUNTIME_KEYS = (
    "_logical_reply_id",
    "_last_outbound_delivery",
    "_delivery_succeeded",
    "_credit_captured_for_turn",
    "_ai_credit_blocked",
    "_ai_turn_started",
)


def reset_turn_runtime_state(user_data: dict[str, Any]) -> None:
    """Remove per-turn evidence before reusing a sender's conversation state."""

    for key in _TURN_RUNTIME_KEYS:
        user_data.pop(key, None)


def _tenant_channel_inbound(user_data: dict[str, Any]) -> tuple[str, str, str, str | None]:
    tenant_id = str(user_data.get("tenant_id") or user_data.get("tenantId") or "").strip().lower()
    channel = str(user_data.get("channel") or "whatsapp").strip().lower()
    external_id = str(
        user_data.get("_source_message_id")
        or user_data.get("source_message_id")
        or user_data.get("_batch_inbound_mids", [""])[-1]
        or ""
    ).strip()
    inbound_event_id = user_data.get("_inbound_event_id")
    return tenant_id, channel, external_id, str(inbound_event_id) if inbound_event_id else None


def ensure_turn_started(
    user_data: dict[str, Any],
    *,
    claim_key_basis: str | None = None,
    external_inbound_id: str | None = None,
) -> str | None:
    """Create or return logical_reply_id for this inbound turn."""
    existing = user_data.get("_logical_reply_id")
    if existing:
        return str(existing)
    tenant_id, channel, discovered_external_id, inbound_event_id = _tenant_channel_inbound(user_data)
    external_id = str(external_inbound_id or discovered_external_id or "").strip()
    if not tenant_id or not external_id:
        return None
    turn = begin_turn(
        tenant_id=tenant_id,
        channel=channel,
        external_inbound_id=external_id,
        inbound_event_id=inbound_event_id,
        claim_key_basis=claim_key_basis,
    )
    user_data["_logical_reply_id"] = turn.logical_reply_id
    user_data["_ai_turn_started"] = True
    return turn.logical_reply_id


def try_reserve_for_ai(user_data: dict[str, Any]) -> bool:
    lid = ensure_turn_started(user_data)
    if not lid:
        return True
    turn = get_turn(lid)
    if turn is None:
        return True
    try:
        reserve_before_ai(turn)
        return True
    except PermissionError:
        user_data["_ai_credit_blocked"] = True
        return False


def on_ai_generated(ctx: dict[str, Any]) -> None:
    """Call after GPT produced bot_reply_text."""
    user_data = ctx.get("user_data") or {}
    lid = user_data.get("_logical_reply_id")
    if not lid:
        return
    flow_meta = ctx.get("flow_meta") or {}
    reply = str(ctx.get("bot_reply_text") or "").strip()
    if not reply:
        release_on_ai_failure(str(lid))
        return
    persist_generated_reply(
        str(lid),
        reply_text=reply,
        model=flow_meta.get("final_response_model") or flow_meta.get("model"),
        prompt_tokens=flow_meta.get("prompt_tokens"),
        completion_tokens=flow_meta.get("completion_tokens"),
        cost_usd=flow_meta.get("cost_usd"),
    )
    capture_after_reply_persisted(
        str(lid),
        prompt_tokens=flow_meta.get("prompt_tokens"),
        completion_tokens=flow_meta.get("completion_tokens"),
        cost_usd=flow_meta.get("cost_usd"),
        model=flow_meta.get("final_response_model") or flow_meta.get("model"),
    )
    user_data["_credit_captured_for_turn"] = True


def on_ai_failed(ctx: dict[str, Any]) -> None:
    user_data = ctx.get("user_data") or {}
    lid = user_data.get("_logical_reply_id")
    if lid:
        release_on_ai_failure(str(lid))


def finalize_delivery(ctx: dict[str, Any]) -> dict[str, Any]:
    """Record delivery outcome after send phase. Returns summary for inbound event marking."""
    user_data = ctx.get("user_data") or {}
    lid = user_data.get("_logical_reply_id")
    if not lid:
        return {"delivery": "unknown"}
    evidence = user_data.get("_last_outbound_delivery") or {}
    if not evidence and user_data.get("_delivery_succeeded"):
        evidence = {"success": True, "reason": "implicit_ok"}
    if evidence:
        record_delivery_outcome(str(lid), evidence)
    turn = get_turn(str(lid))
    if turn is None:
        return {"delivery": "unknown"}
    delivered = turn.state == "DELIVERED"
    retryable = bool(turn.delivery_evidence.get("retryable", not delivered))
    terminal = bool(delivered or turn.state in {"PERMANENT_DELIVERY_BLOCK", "NEEDS_OWNER_ACTION"})
    if turn.delivery_evidence and not retryable:
        terminal = True
    return {
        "delivery": "delivered" if delivered else turn.outbound_state or "pending",
        "state": turn.state,
        "logical_reply_id": turn.logical_reply_id,
        "credit_captured": turn.credit_captured,
        "has_saved_reply": bool(turn.generated_reply),
        "retryable": bool(not terminal and retryable),
        "terminal": terminal,
        "provider_message_id_present": bool(turn.delivery_evidence.get("provider_message_id")),
    }


def pending_delivery_for_claim(claim_key_basis: str) -> dict[str, Any] | None:
    """If a prior turn has a saved reply awaiting delivery, return retry payload."""
    turn = find_pending_delivery_turn(claim_key_basis=claim_key_basis)
    if turn is None or not turn.generated_reply:
        return None
    return {
        "logical_reply_id": turn.logical_reply_id,
        "reply_text": turn.generated_reply,
        "state": turn.state,
        "credit_captured": turn.credit_captured,
    }


async def retry_saved_reply_delivery(
    *,
    user_data: dict[str, Any],
    send_message_func: Any,
    user_id: str,
    pending: dict[str, Any],
) -> bool:
    """Send persisted reply without calling OpenAI. Returns True if delivered."""
    from services.ai_reply_delivery import classify_send_result, wrap_tracked_send
    from services.outbound_turn_idempotency import complete_ai_turn_claim

    tracked = wrap_tracked_send(send_message_func, user_data)
    result = await tracked(user_id, pending["reply_text"])
    evidence = classify_send_result(result)
    user_data["_last_outbound_delivery"] = evidence
    record_delivery_outcome(str(pending["logical_reply_id"]), evidence)
    if evidence.get("success"):
        basis = get_turn(str(pending["logical_reply_id"])) or None
        if basis and basis.claim_key_basis:
            await complete_ai_turn_claim(basis.claim_key_basis)
        return True
    return False
