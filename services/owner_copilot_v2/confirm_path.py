"""Confirm-tool path for Owner Copilot V2 (approve_*)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from typing import Any

from services.owner_copilot_v2.cards import card_from_tool
from services.owner_copilot_v2.models import StreamEvent
from services.owner_copilot_v2.provider import collect_sol_text, iter_sol_text_deltas
from services.owner_copilot_v2.tool_dispatch import dispatch_v2_tool

CancelCheck = Callable[[], bool]


async def run_confirm_path(
    *,
    confirm_tool: str,
    tool_args: dict[str, Any] | None,
    tenant_id: str,
    user_id: str,
    role: str,
    text: str,
    context: dict[str, Any],
    reply_lang: str,
    model: str,
    ctx_tokens: int,
    stage: str,
    build_messages: Callable[..., list[dict[str, Any]]],
    done_payload: Callable[..., dict[str, Any]],
    is_cancelled: CancelCheck | None,
    policy: Any | None = None,
) -> AsyncIterator[StreamEvent]:
    from services.model_policy import ModelPolicyDecision, resolve_owner_policy

    args = dict(tool_args or {})
    intent = confirm_tool
    if confirm_tool.startswith("approve_cm_patch:"):
        intent = "approve_cm_patch"
        args["proposal_id"] = confirm_tool.split(":", 1)[1]
    elif confirm_tool.startswith("approve_diagnosis_fix:"):
        intent = "approve_diagnosis_fix"
        args["proposal_id"] = confirm_tool.split(":", 1)[1]
    elif confirm_tool.startswith("approve_smart_answer:"):
        intent = "approve_smart_answer"
        args["proposal_id"] = confirm_tool.split(":", 1)[1]

    turn_policy: ModelPolicyDecision
    if isinstance(policy, ModelPolicyDecision):
        turn_policy = resolve_owner_policy(prior=policy)
    else:
        turn_policy = resolve_owner_policy(
            surface="owner_copilot",
            confirm_tool=confirm_tool,
            intent=intent,
            force_high=True,
        )

    yield StreamEvent(type="status", payload={"id": "tool", "text": f"Running {intent}…"})
    result = await dispatch_v2_tool(
        intent,
        tenant_id=tenant_id,
        user_id=user_id,
        role=role,
        args=args,
        confirmed=True,
        reply_language=reply_lang,
    )
    cards: list[dict[str, Any]] = []
    c = card_from_tool(result.name, result.data if isinstance(result.data, dict) else {}, ok=result.ok)
    if c:
        cards.append(c.to_dict())
        yield StreamEvent(type="card", payload={"card": c.to_dict()})

    fin = build_messages(context=context, user_text=text or intent)
    fin.append(
        {
            "role": "system",
            "content": "Tool result:\n"
            + json.dumps(result.to_dict(), ensure_ascii=False, default=str)[:8000]
            + "\nWrite the natural final answer.",
        }
    )
    parts: list[str] = []
    async for piece in iter_sol_text_deltas(messages=fin, is_cancelled=is_cancelled, policy=turn_policy):
        parts.append(piece)
        yield StreamEvent(type="delta", payload={"text": piece})
    if not parts:
        text_out, _cancelled = await collect_sol_text(messages=fin, is_cancelled=is_cancelled, policy=turn_policy)
        parts = [text_out] if text_out else ["Done."]
        if text_out:
            yield StreamEvent(type="delta", payload={"text": text_out})
    yield StreamEvent(
        type="done",
        payload=done_payload(
            reply_text="".join(parts).strip(),
            tool_calls=[result.to_dict()],
            cards=cards,
            choices=[],
            model=model,
            ctx_tokens=ctx_tokens,
            stage=stage,
            pending_confirmation=result.confirmation_token,
            reason="confirm_tool",
            route={
                "model": turn_policy.model,
                "reasoning_mode": turn_policy.reasoning_mode,
                "reasoning_effort": turn_policy.reasoning_effort,
                "reason": turn_policy.reason,
            },
        ),
    )
