"""Result translation and usage accounting for Owner Copilot V2 turns."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from services.owner_copilot_v2.models import OwnerV2TurnResult


def owner_result_from_done_payload(payload: Mapping[str, Any]) -> OwnerV2TurnResult:
    """Translate the terminal stream payload into the public turn-result model."""
    return OwnerV2TurnResult(
        reply_text=str(payload.get("reply_text") or ""),
        tool_calls=list(payload.get("tool_calls") or []),
        cards=list(payload.get("cards") or []),
        choices=list(payload.get("choices") or []),
        pending_confirmation=payload.get("pending_confirmation"),
        proposed_patch=payload.get("proposed_patch"),
        route=payload.get("route"),
        context_tokens=int(payload.get("context_tokens") or 0),
        setup_stage=payload.get("setup_stage"),
        quick_actions=list(payload.get("quick_actions") or []),
        model=payload.get("model"),
    )


def record_owner_v2_usage(turn_context: Mapping[str, Any], result: OwnerV2TurnResult) -> None:
    """Write a completed V2 turn to the existing owner-chat usage store."""
    try:
        from services.owner_ai_model_router import RouteDecision, owner_chat_usage_tracker

        reply = result.reply_text or ""
        owner_chat_usage_tracker.record(
            tenant_id=str(turn_context.get("tenant_id") or ""),
            user_id=str(turn_context.get("user_id") or ""),
            conversation_id=str(turn_context.get("conversation_id") or ""),
            route=RouteDecision(
                kind="owner_help",
                model=str(result.model or ""),
                reason="owner_copilot_v2",
                max_context_tokens=0,
            ),
            prompt_tokens=int(result.context_tokens or 0),
            completion_tokens=max(1, len(reply) // 4),
            meta={"source": "owner_copilot_v2", "ok": True},
        )
    except Exception:
        return
