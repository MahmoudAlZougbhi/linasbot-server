"""Reserve / settle Customer AI turns on the message ledger."""

from __future__ import annotations

import logging
from typing import Any

from services.brain.ai_reply.ai_reply_lifecycle import (
    AiReplyTurnRecord,
    get_turn,
    mark_state,
    new_reservation_request_id,
    put_turn,
)

logger = logging.getLogger(__name__)


def reserve_before_ai(turn: AiReplyTurnRecord, *, credits: int = 1) -> str | None:
    """Reserve message units before the model call. ``credits`` is a historical alias for units."""
    _ = max(1, int(credits or 1))
    if turn.credit_reservation_id:
        return turn.credit_reservation_id
    tenant_id = turn.tenant_id
    if not tenant_id:
        return None
    request_id = new_reservation_request_id(turn.logical_reply_id)
    try:
        from services.brain.leftover_reserve import reserve_leftover_reply

        rid = reserve_leftover_reply(
            tenant_id=tenant_id,
            request_id=request_id,
            operation_type="customer_ai_reply",
            pin_ids=tuple(
                item
                for item in (
                    turn.logical_reply_id,
                    turn.external_inbound_id,
                    turn.inbound_event_id,
                )
                if item
            ),
        )
        if not rid:
            raise PermissionError("insufficient_messages")
        turn.credit_reservation_id = rid
        turn.state = "AI_PROCESSING"
        put_turn(turn)
        return rid
    except PermissionError:
        raise
    except Exception as exc:
        logger.warning("[ai_reply_credit] reserve_failed tenant=%s type=%s", tenant_id, type(exc).__name__)
        raise PermissionError("Message reservation failed") from exc


def capture_after_reply_persisted(
    logical_reply_id: str,
    *,
    provider_cost_usd: float | None = None,
    model_provider: str | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    cost_usd: float | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    turn = get_turn(logical_reply_id)
    if turn is None:
        return {"skipped": True, "reason": "turn_missing"}
    if turn.credit_captured:
        return {"duplicate": True, "op": "capture", "logical_reply_id": logical_reply_id}

    capture_ref = f"capture:{logical_reply_id}"
    result: dict[str, Any] = {"logical_reply_id": logical_reply_id}
    _ = (provider_cost_usd, prompt_tokens, completion_tokens, cost_usd)

    if turn.credit_reservation_id:
        from services.brain.leftover_reserve import capture_leftover_reply

        ok = capture_leftover_reply(
            turn.tenant_id,
            turn.credit_reservation_id,
            model_provider=model_provider or model or turn.model or "customer_ai_reply",
        )
        if not ok:
            result["pending_settlement"] = True
            return result
        result["captured"] = True
    else:
        result["skipped"] = True
        result["reason"] = "no_credit_reservation"

    turn.credit_captured = True
    turn.credit_capture_ref = capture_ref
    turn.state = "CREDIT_CAPTURED_ONCE"
    put_turn(turn)
    mark_state(logical_reply_id, "CREDIT_CAPTURED_ONCE", credit_captured=True, credit_capture_ref=capture_ref)
    return result


def release_on_ai_failure(logical_reply_id: str) -> dict[str, Any]:
    turn = get_turn(logical_reply_id)
    if turn is None:
        return {"skipped": True}
    if turn.credit_captured:
        return {"skipped": True, "reason": "already_captured"}
    rid = turn.credit_reservation_id
    if rid and turn.tenant_id:
        try:
            from services.brain.leftover_reserve import release_leftover_reply

            release_leftover_reply(turn.tenant_id, rid)
            mark_state(logical_reply_id, "NO_FINAL_CHARGE", last_error=turn.last_error)
            return {"op": "release", "released": True}
        except Exception as exc:
            logger.warning("[ai_reply_credit] release_failed type=%s", type(exc).__name__)
    mark_state(logical_reply_id, "AI_RETRY_REQUIRED")
    return {"op": "release", "skipped": not bool(rid)}
