"""Credit capture gate — reserve before AI, capture once after reply persisted, release on AI fail."""

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
    """Reserve credits/tokens before model call. Returns reservation_id or None for wallet-only path."""
    if turn.credit_reservation_id:
        return turn.credit_reservation_id
    tenant_id = turn.tenant_id
    if not tenant_id:
        return None
    request_id = new_reservation_request_id(turn.logical_reply_id)
    try:
        from services.billing.credit_ledger_service import credit_ledger_service

        credit_ledger_service.ensure_period_grant(tenant_id)
        rid = credit_ledger_service.reserve(
            tenant_id=tenant_id,
            user_id=None,
            credits=credits,
            operation_type="customer_ai_reply",
            request_id=request_id,
        )
        from services.billing.membership.pending_settlement import record_hold
        from services.brain.leftover_reserve import _pin

        aliases: list[str] = []
        for item in (
            request_id,
            rid,
            turn.logical_reply_id,
            turn.external_inbound_id,
            turn.inbound_event_id,
        ):
            text = str(item or "").strip()
            if text and text not in aliases:
                aliases.append(text)
        record_hold(
            tenant_id=tenant_id,
            reservation_id=rid,
            operation_id=request_id,
            billing_policy="legacy_credits",
            channel="customer_ai_reply",
            extra={"operation_type": "customer_ai_reply", "candidate_ids": aliases},
        )
        _pin(
            tenant_id,
            *[
                item
                for item in (request_id, rid, turn.logical_reply_id, turn.external_inbound_id, turn.inbound_event_id)
                if item
            ],
        )
        from services.billing.membership.credit_reservation_index import record_open

        record_open(
            tenant_id=tenant_id,
            reservation_id=rid,
            request_id=request_id,
            operation_type="customer_ai_reply",
        )
        turn.credit_reservation_id = rid
        turn.state = "AI_PROCESSING"
        put_turn(turn)
        return rid
    except PermissionError:
        raise
    except Exception as exc:
        logger.warning("[ai_reply_credit] reserve_failed tenant=%s type=%s", tenant_id, type(exc).__name__)
        raise PermissionError("Credit reservation failed") from exc


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
    """Capture exactly once when reply is persisted. Uses the credit ledger reservation."""
    turn = get_turn(logical_reply_id)
    if turn is None:
        return {"skipped": True, "reason": "turn_missing"}
    if turn.credit_captured:
        return {"duplicate": True, "op": "capture", "logical_reply_id": logical_reply_id}

    capture_ref = f"capture:{logical_reply_id}"
    result: dict[str, Any] = {"logical_reply_id": logical_reply_id}

    if turn.credit_reservation_id:
        from services.billing.credit_ledger_service import credit_ledger_service

        try:
            cap = credit_ledger_service.capture(
                tenant_id=turn.tenant_id,
                reservation_id=turn.credit_reservation_id,
                provider_cost_usd=provider_cost_usd or turn.cost_usd,
                model_provider=model_provider or model or turn.model,
            )
            result.update(cap)
            try:
                from services.brain.leftover_reserve import complete_leftover_capture

                complete_leftover_capture(
                    turn.tenant_id,
                    turn.credit_reservation_id,
                    operation_id=logical_reply_id,
                    extra_ids=[item for item in (turn.external_inbound_id, turn.inbound_event_id) if item],
                )
            except Exception:
                pass
        except Exception:
            from services.billing.membership.reservation_reconcile import hold_failed_capture_after_send

            hold_failed_capture_after_send(
                tenant_id=turn.tenant_id,
                reservation_id=turn.credit_reservation_id,
                operation_id=logical_reply_id,
                billing_policy="legacy_credits",
                channel=model_provider or model or "customer_ai_reply",
            )
            from services.billing.membership.credit_reservation_index import mark_closed

            mark_closed(turn.credit_reservation_id, state="pending_settlement")
            result["pending_settlement"] = True
            return result
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
    """Release reservation when OpenAI fails before a valid reply — no final capture."""
    turn = get_turn(logical_reply_id)
    if turn is None:
        return {"skipped": True}
    if turn.credit_captured:
        return {"skipped": True, "reason": "already_captured"}
    rid = turn.credit_reservation_id
    if rid and turn.tenant_id:
        try:
            from services.billing.credit_ledger_service import credit_ledger_service

            out = credit_ledger_service.release(tenant_id=turn.tenant_id, reservation_id=rid)
            from services.billing.membership.credit_reservation_index import mark_closed
            from services.billing.membership.pending_settlement import get_pending, upsert
            from services.brain.leftover_reserve import _unpin

            held = get_pending(turn.tenant_id, rid)
            aliases = [rid, logical_reply_id, turn.external_inbound_id, turn.inbound_event_id]
            if held is not None:
                aliases.append(held.operation_id)
                aliases.extend(str(item or "") for item in (held.extra.get("candidate_ids") or []))
            _unpin(turn.tenant_id, *[item for item in aliases if item])
            mark_closed(rid, state="released")
            upsert(
                tenant_id=turn.tenant_id,
                reservation_id=rid,
                operation_id=held.operation_id if held is not None else logical_reply_id,
                billing_policy="legacy_credits",
                state="released",
                reason="unused_or_failed_before_send",
            )
            mark_state(logical_reply_id, "NO_FINAL_CHARGE", last_error=turn.last_error)
            return out
        except Exception as exc:
            logger.warning("[ai_reply_credit] release_failed type=%s", type(exc).__name__)
    mark_state(logical_reply_id, "AI_RETRY_REQUIRED")
    return {"op": "release", "skipped": not bool(rid)}
