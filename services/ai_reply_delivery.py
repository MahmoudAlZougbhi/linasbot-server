"""Outbound delivery classification and send wrappers for AI reply turns."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

SendFunc = Callable[..., Awaitable[Any]]

PERMANENT_ERROR_MARKERS = (
    "policy",
    "blocked",
    "permission",
    "not authorized",
    "oauth",
    "disconnected",
    "#200",
    "#10",
)


def classify_send_result(result: Any) -> dict[str, Any]:
    """Normalize provider send results into delivery evidence."""
    if result is None:
        return {"success": False, "retryable": True, "reason": "null_result"}
    if isinstance(result, dict):
        if result.get("skipped_stale_text_turn"):
            return {"success": False, "retryable": False, "reason": "stale_turn_skip"}
        if result.get("duplicate_suppressed"):
            return {
                "success": False,
                "retryable": False,
                "duplicate_suppressed": True,
                "reason": "meta_outbound_duplicate_suppressed",
            }
        if result.get("needs_owner_action"):
            return {
                "success": False,
                "retryable": False,
                "needs_owner_action": True,
                "reason": "meta_outbound_ambiguous_needs_owner_action",
            }
        if result.get("simulated"):
            return {"success": True, "retryable": False, "reason": "simulated", "delivered_externally": False}
        if result.get("success") is True:
            provider_message_id = result.get("message_id") or result.get("id")
            if result.get("provider") == "meta" and not str(provider_message_id or "").strip():
                return {
                    "success": False,
                    "retryable": True,
                    "reason": "meta_send_missing_message_id",
                }
            return {
                "success": True,
                "retryable": False,
                "provider_message_id": provider_message_id,
                "raw": {k: result.get(k) for k in ("message_id", "id", "recipient_id") if k in result},
            }
        err = str(result.get("error") or result.get("error_message") or "")
        low = err.lower()
        permanent = any(m in low for m in PERMANENT_ERROR_MARKERS)
        return {
            "success": False,
            "retryable": not permanent,
            "permanent_block": permanent,
            "reason": err[:500] or "send_failed",
        }
    return {"success": True, "retryable": False, "reason": "non_dict_assumed_ok"}


def wrap_tracked_send(raw_send: SendFunc, user_data: dict[str, Any]) -> SendFunc:
    """Wrap send_message_func to record last outbound delivery evidence on user_data."""

    async def _tracked(
        to_number: str,
        message_text: str | None = None,
        image_url: str | None = None,
        audio_url: str | None = None,
    ) -> Any:
        result = await raw_send(
            to_number,
            message_text=message_text,
            image_url=image_url,
            audio_url=audio_url,
        )
        evidence = classify_send_result(result)
        user_data["_last_outbound_delivery"] = evidence
        if evidence.get("success"):
            user_data["_delivery_succeeded"] = True
        else:
            user_data["_delivery_succeeded"] = False
        return result

    return _tracked


def record_delivery_outcome(logical_reply_id: str, evidence: dict[str, Any]) -> None:
    from services.ai_reply_lifecycle import get_turn, put_turn

    rec = get_turn(logical_reply_id)
    if rec is None:
        return
    rec.delivery_evidence = evidence
    rec.last_error = None if evidence.get("success") else str(evidence.get("reason") or "delivery_failed")
    if evidence.get("provider_message_id"):
        rec.provider_reply_id = str(evidence["provider_message_id"])
    if evidence.get("success"):
        rec.state = "DELIVERED"
        rec.outbound_state = "delivered"
    elif evidence.get("needs_owner_action"):
        rec.state = "NEEDS_OWNER_ACTION"
        rec.outbound_state = "needs_owner_action"
    elif evidence.get("duplicate_suppressed"):
        rec.state = "PERMANENT_DELIVERY_BLOCK"
        rec.outbound_state = "duplicate_suppressed"
    elif evidence.get("permanent_block"):
        rec.state = "PERMANENT_DELIVERY_BLOCK"
        rec.outbound_state = "permanent_block"
    elif evidence.get("retryable", True):
        rec.state = "OUTBOUND_RETRY"
        rec.outbound_state = "retry"
        rec.retry_count += 1
    else:
        rec.state = "OUTBOUND_RETRY"
        rec.outbound_state = "failed"
        rec.retry_count += 1
    put_turn(rec)
