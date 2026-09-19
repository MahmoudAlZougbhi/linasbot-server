"""Sol owner brain: structured tool calling → results → streamed natural final answer."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable
from typing import Any, Literal

from services.owner_copilot.brain_stream_body import MAX_TOOL_ROUNDS, _iter_owner_turn_v2_events_body  # noqa: F401
from services.owner_copilot.flags import owner_copilot_v2_enabled
from services.owner_copilot.models import StreamEvent
from services.owner_copilot.provider import iter_sol_tool_round  # noqa: F401

CancelCheck = Callable[[], bool]


async def iter_owner_turn_v2_events(
    *,
    tenant_id: str,
    user_id: str,
    role: str,
    conversation_id: str,
    user_text: str,
    confirm_tool: str | None = None,
    confirm_billing: bool = False,
    messages: list[dict[str, Any]] | None = None,
    tool_args: dict[str, Any] | None = None,
    choice_id: str | None = None,
    choice_set_id: str | None = None,
    attachment_ids: list[str] | None = None,
    owner_mode: Literal["chat", "work"] | None = None,
    reply_language: str | None = None,
    revise_proposal_id: str | None = None,
    is_cancelled: CancelCheck | None = None,
) -> AsyncGenerator[StreamEvent, None]:
    if not owner_copilot_v2_enabled():
        yield StreamEvent(type="error", payload={"message": "OWNER_COPILOT_V2 disabled"})
        return

    from services.billing.credit_ai_gate import owner_credits_paused_payload
    from services.owner_copilot.message_billing import (
        confirm_copy,
        estimate_copilot_cost_usd,
        owner_turn_hold_abort,
        owner_turn_hold_begin,
        owner_turn_hold_on_event,
    )

    history_tokens = sum(len(str((m or {}).get("content") or "")) for m in (messages or [])) // 4
    turn_hold = owner_turn_hold_begin(
        tenant_id,
        conversation_id=conversation_id,
        user_text=user_text,
        confirm_tool=confirm_tool,
        choice_id=choice_id,
        attachment_ids=attachment_ids,
        estimated_usd=estimate_copilot_cost_usd(
            user_text=user_text,
            history_tokens=history_tokens,
            attachment_count=len(attachment_ids or []),
        ),
        confirm_billing=confirm_billing,
    )
    if turn_hold.blocked:
        yield StreamEvent(
            type="credits_paused",
            payload=owner_credits_paused_payload(tenant_id, need=turn_hold.units),
        )
        return
    if turn_hold.confirm_required:
        yield StreamEvent(
            type="billing_confirm",
            payload={
                "code": "confirm_messages",
                "units": turn_hold.units,
                "message": confirm_copy(units=turn_hold.units, language=reply_language or "en"),
            },
        )
        return

    try:
        async for _ev in _iter_owner_turn_v2_events_body(
            tenant_id=tenant_id,
            user_id=user_id,
            role=role,
            conversation_id=conversation_id,
            user_text=user_text,
            confirm_tool=confirm_tool,
            messages=messages,
            tool_args=tool_args,
            choice_id=choice_id,
            choice_set_id=choice_set_id,
            attachment_ids=attachment_ids,
            owner_mode=owner_mode,
            reply_language=reply_language,
            revise_proposal_id=revise_proposal_id,
            is_cancelled=is_cancelled,
        ):
            actual_usd = None
            if _ev.type == "done":
                from services.brain.model_pricing import compute_cost_from_usage
                from services.owner_copilot.flags import owner_model_name

                prompt = int(_ev.payload.get("context_tokens") or 0)
                completion = max(1, len(str(_ev.payload.get("reply_text") or "")) // 4)
                actual_usd = float(compute_cost_from_usage(owner_model_name(), prompt, completion)["cost_usd"])
            owner_turn_hold_on_event(turn_hold, _ev.type, actual_usd=actual_usd)
            yield _ev
    finally:
        owner_turn_hold_abort(turn_hold)


def __getattr__(name: str) -> Any:
    if name == "run_owner_turn_v2":
        from services.owner_copilot.brain_run import run_owner_turn_v2 as _run_owner_turn_v2

        return _run_owner_turn_v2
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
