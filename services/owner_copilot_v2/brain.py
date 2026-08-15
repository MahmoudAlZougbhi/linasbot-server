"""Sol owner brain: structured tool calling → results → streamed natural final answer."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable
from typing import Any, Literal

from services.owner_copilot_v2.brain_stream_body import _iter_owner_turn_v2_events_body, MAX_TOOL_ROUNDS
from services.owner_copilot_v2.flags import owner_copilot_v2_enabled
from services.owner_copilot_v2.models import StreamEvent
from services.owner_copilot_v2.provider import iter_sol_text_deltas, iter_sol_tool_round

CancelCheck = Callable[[], bool]


async def iter_owner_turn_v2_events(
    *,
    tenant_id: str,
    user_id: str,
    role: str,
    conversation_id: str,
    user_text: str,
    confirm_tool: str | None = None,
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

    from services.credit_ai_gate import owner_credits_paused_payload
    from services.owner_copilot_credit import (
        owner_turn_credit_abort,
        owner_turn_credit_begin,
        owner_turn_credit_on_event,
    )

    turn_credit = owner_turn_credit_begin(tenant_id, conversation_id=conversation_id)
    if turn_credit.blocked:
        yield StreamEvent(type="credits_paused", payload=owner_credits_paused_payload(tenant_id))
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
            owner_turn_credit_on_event(turn_credit, _ev.type)
            yield _ev
    finally:
        owner_turn_credit_abort(turn_credit)


def __getattr__(name: str) -> Any:
    if name == "run_owner_turn_v2":
        from services.owner_copilot_v2.brain_run import run_owner_turn_v2 as _run_owner_turn_v2

        return _run_owner_turn_v2
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
