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
    tool_calls: list[dict[str, Any]] = [result.to_dict()]
    c = card_from_tool(result.name, result.data if isinstance(result.data, dict) else {}, ok=result.ok)
    if c:
        cards.append(c.to_dict())
        yield StreamEvent(type="card", payload={"card": c.to_dict()})

    pending_confirmation = result.confirmation_token
    continue_blob: dict[str, Any] | None = None
    if intent == "approve_cm_patch" and result.ok:
        from services.owner_copilot_v2.cm_approve_continue import continue_after_cm_approve

        approved_section = None
        live = None
        if isinstance(result.data, dict):
            approved_section = str(result.data.get("section") or "") or None
            if "live" in result.data:
                live = bool(result.data.get("live"))
            else:
                activation = result.data.get("activation")
                if isinstance(activation, dict) and "activated" in activation:
                    live = bool(activation.get("activated"))
        yield StreamEvent(type="status", payload={"id": "continue", "text": "Continuing setup…"})
        continue_blob = await continue_after_cm_approve(
            tenant_id=tenant_id,
            user_id=user_id,
            role=role,
            approved_ok=True,
            approved_section=approved_section,
            live=live,
        )
        next_prop = continue_blob.get("next_proposal")
        if isinstance(next_prop, dict) and next_prop.get("ok"):
            tool_calls.append(next_prop)
            raw_data = next_prop.get("data")
            ndata: dict[str, Any] = raw_data if isinstance(raw_data, dict) else {}
            nc = card_from_tool(str(next_prop.get("name") or "propose_cm_patch"), ndata, ok=True)
            if nc:
                cards.append(nc.to_dict())
                yield StreamEvent(type="card", payload={"card": nc.to_dict()})
            pending_confirmation = next_prop.get("confirmation_token") or pending_confirmation

    fin = build_messages(context=context, user_text=text or intent)
    fin_bits = [
        "Tool result:\n" + json.dumps(result.to_dict(), ensure_ascii=False, default=str)[:8000],
    ]
    if continue_blob:
        fin_bits.append(
            "Continue context:\n"
            + json.dumps(continue_blob, ensure_ascii=False, default=str)[:6000]
            + "\n"
            + str(continue_blob.get("directive") or "")
        )
    fin_bits.append("Write the natural final answer.")
    fin.append({"role": "system", "content": "\n".join(fin_bits)})
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
            tool_calls=tool_calls,
            cards=cards,
            choices=[],
            model=model,
            ctx_tokens=ctx_tokens,
            stage=stage,
            pending_confirmation=pending_confirmation,
            reason="confirm_tool",
            route={
                "model": turn_policy.model,
                "reasoning_mode": turn_policy.reasoning_mode,
                "reasoning_effort": turn_policy.reasoning_effort,
                "reason": turn_policy.reason,
            },
        ),
    )
