"""Sol owner brain: structured tool calling → results → streamed natural final answer."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator, Callable
from typing import Any, Literal

from services.model_policy import emit_model_policy_trace, owner_stream_route_payload, resolve_owner_policy
from services.owner_ai_context import pack_owner_turn_context
from services.owner_copilot_v2.assent import looks_like_owner_assent, resolve_pending_confirm_token
from services.owner_copilot_v2.brain_support import (
    FINAL_ANSWER_NUDGE,
    _build_messages,
    done_payload,
    emit_as_deltas,
    status_label,
)
from services.owner_copilot_v2.cards import card_from_tool
from services.owner_copilot_v2.choices import choices_from_tool_result, make_choice_set
from services.owner_copilot_v2.confirm_path import run_confirm_path
from services.owner_copilot_v2.creative_policy import creative_refusal_message, looks_like_creative_request
from services.owner_copilot_v2.flags import owner_copilot_v2_enabled, owner_model_name
from services.owner_copilot_v2.models import ChatChoice, StreamEvent
from services.owner_copilot_v2.proposal_revise import load_proposal_revise_context, supersede_revised_proposal
from services.owner_copilot_v2.provider import iter_sol_text_deltas, iter_sol_tool_round
from services.owner_copilot_v2.tool_dispatch import dispatch_v2_tool, tool_result_for_model

CancelCheck = Callable[[], bool]
# Full CM walks need enough rounds to cover every section + article/FAQ chunk continuation.
MAX_TOOL_ROUNDS = 10


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

    from services.credit_ai_gate import ai_generation_blocked, owner_credits_paused_payload

    if ai_generation_blocked(tenant_id):
        yield StreamEvent(type="credits_paused", payload=owner_credits_paused_payload(tenant_id))
        return

    text = (user_text or "").strip()
    # Natural assent (ok / موافق / yes / …) on a pending Draft proposal → confirm path.
    # Never invent a token; only resolve an existing pending confirmation.
    # Edit-chip revision must not be treated as Approve assent.
    if not confirm_tool and not revise_proposal_id and looks_like_owner_assent(text):
        confirm_tool = resolve_pending_confirm_token(
            tenant_id=tenant_id,
            user_id=user_id,
            messages=messages,
        )
    context = pack_owner_turn_context(
        tenant_id=tenant_id,
        user_id=user_id,
        user_text=text or (confirm_tool or choice_id or ""),
        messages=messages,
        reply_language=reply_language,
    )
    context["recent_messages_raw"] = list(messages or [])
    if revise_proposal_id and not confirm_tool:
        revise_ctx = load_proposal_revise_context(
            tenant_id=tenant_id,
            user_id=user_id,
            revise_proposal_id=str(revise_proposal_id),
        )
        if revise_ctx:
            context["proposal_revise"] = revise_ctx
            tool_args = {**(tool_args or {}), "replace_proposal_id": revise_ctx["proposal_id"]}
    stage = str((context.get("account_summary") or {}).get("setup_stage") or "")
    reply_lang = str(context.get("reply_language") or "en")
    attachment_action: Literal["none", "analyze", "import"] | None = None
    if attachment_ids:
        # Attachment alone does not force high; import/apply paths set import via extract tool.
        attachment_action = "analyze"
    mode = owner_mode if owner_mode in ("chat", "work") else None
    policy = resolve_owner_policy(
        surface="owner_copilot",
        confirm_tool=confirm_tool,
        user_text=text,
        attachment_action=attachment_action,
        force_high=bool(confirm_tool or revise_proposal_id),
        owner_mode=mode,
    )
    model = policy.model or owner_model_name()
    emit_model_policy_trace(policy, extra={"conversation_id_hash": conversation_id[:12]})
    ctx_tokens = max(1, len(json.dumps(context, ensure_ascii=False, default=str)) // 4)

    yield StreamEvent(type="thinking", payload={"label": "Thinking…"})
    if is_cancelled and is_cancelled():
        yield StreamEvent(type="cancelled", payload={"reply_text": ""})
        return

    if choice_id and choice_set_id:
        from services.owner_copilot_v2.choices import resolve_choice

        resolved = resolve_choice(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            choice_set_id=choice_set_id,
            choice_id=choice_id,
        )
        if not resolved.get("ok"):
            yield StreamEvent(type="error", payload={"message": str(resolved.get("error") or "choice_rejected")})
            return
        choice = resolved["choice"]
        text = text or str(choice.get("label") or choice_id)
        tool_args = {**(tool_args or {}), **(choice.get("payload") or {}), "choice_action": choice.get("action")}

    if confirm_tool:
        async for ev in run_confirm_path(
            confirm_tool=confirm_tool,
            tool_args=tool_args,
            tenant_id=tenant_id,
            user_id=user_id,
            role=role,
            text=text,
            context=context,
            reply_lang=reply_lang,
            model=model,
            ctx_tokens=ctx_tokens,
            stage=stage,
            build_messages=_build_messages,
            done_payload=done_payload,
            is_cancelled=is_cancelled,
            policy=policy,
        ):
            yield ev
        return

    if not text and not (attachment_ids or []):
        msg = "Tell me what you’d like to configure or inspect."
        yield StreamEvent(type="delta", payload={"text": msg})
        yield StreamEvent(
            type="done",
            payload=done_payload(
                reply_text=msg,
                tool_calls=[],
                cards=[],
                choices=[],
                model=model,
                ctx_tokens=ctx_tokens,
                stage=stage,
                reason="empty",
            ),
        )
        return

    if looks_like_creative_request(text):
        msg = creative_refusal_message(language=reply_lang)
        async for ev in emit_as_deltas(msg):
            yield ev
        yield StreamEvent(
            type="done",
            payload=done_payload(
                reply_text=msg,
                tool_calls=[],
                cards=[],
                choices=[],
                model=model,
                ctx_tokens=ctx_tokens,
                stage=stage,
                reason="creative_cancelled",
            ),
        )
        return

    if attachment_ids:
        tool_args = {**(tool_args or {}), "attachment_id": attachment_ids[0]}

    chat_messages = _build_messages(
        context=context,
        user_text=text,
        attachment_ids=attachment_ids,
        tenant_id=tenant_id,
    )
    tool_calls_acc: list[dict[str, Any]] = []
    cards_acc: list[dict[str, Any]] = []
    choices_acc: list[dict[str, Any]] = []
    proposed_patch = None
    pending_confirmation = None

    try:
        for _ in range(MAX_TOOL_ROUNDS):
            if is_cancelled and is_cancelled():
                yield StreamEvent(type="cancelled", payload={"reply_text": ""})
                return

            turn_policy = resolve_owner_policy(prior=policy)
            # Stream the tool-aware round so text-only answers write token-by-token (ChatGPT-like).
            streamed_parts: list[str] = []
            round_result = None
            async for kind, payload in iter_sol_tool_round(
                messages=chat_messages,
                is_cancelled=is_cancelled,
                policy=turn_policy,
            ):
                if kind == "delta":
                    streamed_parts.append(str(payload))
                    yield StreamEvent(type="delta", payload={"text": str(payload)})
                else:
                    round_result = payload

            if is_cancelled and is_cancelled():
                yield StreamEvent(type="cancelled", payload={"reply_text": "".join(streamed_parts)})
                return

            tcalls = list(getattr(round_result, "tool_calls", None) or [])
            round_content = str(getattr(round_result, "content", None) or "").strip()

            if not tcalls:
                reply_text = round_content or "".join(streamed_parts).strip()
                if not reply_text:
                    reply_parts: list[str] = []
                    async for delta_text in iter_sol_text_deltas(
                        messages=chat_messages,
                        is_cancelled=is_cancelled,
                        policy=turn_policy,
                    ):
                        reply_parts.append(delta_text)
                        yield StreamEvent(type="delta", payload={"text": delta_text})
                    reply_text = "".join(reply_parts).strip()
                choice_set_id_out = None
                choices_out = choices_acc
                if choices_acc:
                    built = [
                        ChatChoice(id=c["id"], label=c["label"], action=c["action"], payload=c.get("payload") or {})
                        for c in choices_acc
                    ]
                    choice_payload = make_choice_set(
                        tenant_id=tenant_id, conversation_id=conversation_id, choices=built
                    )
                    choice_set_id_out = choice_payload.get("choice_set_id")
                    choices_out = choice_payload.get("choices") or choices_acc
                    yield StreamEvent(type="choices", payload=choice_payload)
                yield StreamEvent(
                    type="done",
                    payload=done_payload(
                        reply_text=reply_text,
                        tool_calls=tool_calls_acc,
                        cards=cards_acc,
                        choices=choices_out,
                        model=model,
                        ctx_tokens=ctx_tokens,
                        stage=stage,
                        pending_confirmation=pending_confirmation,
                        proposed_patch=proposed_patch,
                        choice_set_id=choice_set_id_out,
                        route=owner_stream_route_payload(turn_policy),
                    ),
                )
                return

            chat_messages.append(
                {
                    "role": "assistant",
                    "content": round_content or None,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments or "{}",
                            },
                        }
                        for tc in tcalls
                    ],
                }
            )
            for tc in tcalls:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                if tool_args:
                    for k, v in tool_args.items():
                        args.setdefault(k, v)
                yield StreamEvent(type="status", payload={"id": name, "text": status_label(name)})
                result = await dispatch_v2_tool(
                    name,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    role=role,
                    args=args,
                    confirmed=False,
                    reply_language=reply_lang,
                )
                tool_calls_acc.append(result.to_dict())
                chat_messages.append({"role": "tool", "tool_call_id": tc.id, "content": tool_result_for_model(result)})
                card = card_from_tool(result.name, result.data if isinstance(result.data, dict) else {}, ok=result.ok)
                if card:
                    cards_acc.append(card.to_dict())
                    yield StreamEvent(type="card", payload={"card": card.to_dict()})
                for ch in choices_from_tool_result(result.name, result.data if isinstance(result.data, dict) else {}):
                    choices_acc.append(ch.to_dict())
                if (
                    result.name
                    in {
                        "propose_cm_patch",
                        "propose_cm_article_upsert",
                        "propose_cm_faq_upsert",
                        "propose_cm_delete",
                        "propose_smart_answer",
                    }
                    and result.ok
                    and isinstance(result.data, dict)
                ):
                    proposed_patch = {
                        "proposal_id": result.data.get("proposal_id"),
                        "confirmation_token": result.data.get("confirmation_token"),
                        "preview": result.data.get("preview"),
                    }
                    pending_confirmation = result.confirmation_token
                    supersede_revised_proposal(
                        tenant_id=tenant_id,
                        user_id=user_id,
                        context=context,
                        new_proposal_id=str(result.data.get("proposal_id") or "") or None,
                    )

        fin_messages = list(chat_messages)
        fin_messages.append({"role": "system", "content": FINAL_ANSWER_NUDGE})
        fin_policy = resolve_owner_policy(prior=policy)
        parts: list[str] = []
        async for delta_text in iter_sol_text_deltas(
            messages=fin_messages, is_cancelled=is_cancelled, policy=fin_policy
        ):
            parts.append(delta_text)
            yield StreamEvent(type="delta", payload={"text": delta_text})
        yield StreamEvent(
            type="done",
            payload=done_payload(
                reply_text="".join(parts).strip(),
                tool_calls=tool_calls_acc,
                cards=cards_acc,
                choices=choices_acc,
                model=model,
                ctx_tokens=ctx_tokens,
                stage=stage,
                pending_confirmation=pending_confirmation,
                proposed_patch=proposed_patch,
                reason="max_tool_rounds",
                route=owner_stream_route_payload(fin_policy),
            ),
        )
    except Exception as exc:  # noqa: BLE001
        from services.llm_core_service import sanitize_llm_error

        yield StreamEvent(
            type="error",
            payload={
                "message": f"Linas AI is temporarily unavailable. Please retry ({sanitize_llm_error(exc)}).",
                "retryable": True,
            },
        )


def __getattr__(name: str) -> Any:
    if name == "run_owner_turn_v2":
        from services.owner_copilot_v2.brain_run import run_owner_turn_v2 as _run_owner_turn_v2

        return _run_owner_turn_v2
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
