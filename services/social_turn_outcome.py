"""Build Meta social turn outcomes after handle_message returns."""

from __future__ import annotations

from typing import Any


def deferred_combine_outcome(user_data: dict[str, Any]) -> dict[str, Any] | None:
    if user_data.get("_distributed_combine_scheduled"):
        return {
            "ok": True,
            "delivery": "combine_scheduled",
            "retryable": False,
            "terminal": False,
            "deferred": True,
            "logical_reply_id": None,
        }
    if user_data.get("_combine_outcome") == "superseded":
        return {
            "ok": True,
            "delivery": "combine_superseded",
            "retryable": False,
            "terminal": False,
            "deferred": True,
            "logical_reply_id": None,
        }
    return None


def finalize_social_turn(user_data: dict[str, Any]) -> dict[str, Any]:
    from services.ai_reply_turn_runtime import finalize_delivery

    delivery_summary = finalize_delivery({"user_data": user_data})
    combined_ids = list(user_data.get("_combine_event_ids") or [])
    return {
        "ok": True,
        "delivery": delivery_summary.get("delivery", "unknown"),
        "logical_reply_id": delivery_summary.get("logical_reply_id"),
        "credit_captured": delivery_summary.get("credit_captured"),
        "retryable": delivery_summary.get("retryable", True),
        "terminal": delivery_summary.get("terminal", False),
        "provider_message_id_present": delivery_summary.get("provider_message_id_present", False),
        "combined_event_ids": combined_ids,
    }
