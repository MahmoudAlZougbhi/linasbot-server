"""Owner Copilot turn orchestration — Sol / owner_copilot_v2 only."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class OwnerTurnResult:
    reply_text: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    pending_confirmation: str | None = None
    proposed_patch: dict[str, Any] | None = None
    creative_draft: dict[str, Any] | None = None
    route: dict[str, Any] | None = None
    context_tokens: int = 0
    setup_stage: str | None = None
    quick_actions: list[dict[str, str]] = field(default_factory=list)
    cards: list[dict[str, Any]] = field(default_factory=list)
    choices: list[dict[str, Any]] = field(default_factory=list)
    model: str | None = None


async def run_owner_turn(
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
) -> OwnerTurnResult:
    from services.credit_ai_gate import ai_generation_blocked, owner_credits_paused_payload
    from services.owner_copilot.brain_run import run_owner_turn_v2

    if ai_generation_blocked(tenant_id):
        paused = owner_credits_paused_payload(tenant_id)
        return OwnerTurnResult(reply_text="", route={"reason": "insufficient_credits", **paused})

    v2 = await run_owner_turn_v2(
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
    )
    return OwnerTurnResult(
        reply_text=v2.reply_text,
        tool_calls=v2.tool_calls,
        pending_confirmation=v2.pending_confirmation,
        proposed_patch=v2.proposed_patch,
        creative_draft=None,
        route=v2.route,
        context_tokens=v2.context_tokens,
        setup_stage=v2.setup_stage,
        quick_actions=v2.quick_actions,
        cards=list(v2.cards or []),
        choices=list(v2.choices or []),
        model=v2.model,
    )
