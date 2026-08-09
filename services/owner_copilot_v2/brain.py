"""Sol owner brain: structured tool calling → results → streamed natural final answer."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from typing import Any

from services.owner_ai_context import pack_owner_turn_context
from services.owner_copilot_v2.cards import card_from_tool
from services.owner_copilot_v2.choices import choices_from_tool_result, make_choice_set
from services.owner_copilot_v2.confirm_path import run_confirm_path
from services.owner_copilot_v2.creative_policy import creative_refusal_message, looks_like_creative_request
from services.owner_copilot_v2.flags import owner_context_token_budget, owner_copilot_v2_enabled, owner_model_name
from services.owner_copilot_v2.memory import pack_recent_messages
from services.owner_copilot_v2.models import ChatChoice, OwnerV2TurnResult, StreamEvent
from services.owner_copilot_v2.provider import iter_sol_text_deltas, sol_chat_completion
from services.owner_copilot_v2.tool_dispatch import dispatch_v2_tool, tool_result_for_model
from services.owner_copilot_v2.tool_schemas import OWNER_V2_TOOL_SCHEMAS

CancelCheck = Callable[[], bool]
MAX_TOOL_ROUNDS = 4

SYSTEM_V2 = (
    "You are Linas AI System Copilot — one brain for the authenticated business owner. "
    "Customer scope: Instagram/Facebook DMs and comments only. Creative/posts/images/videos are cancelled. "
    "Use typed tools for account, CM, integrations, diagnosis, setup, and price-list extraction. "
    "Never claim a tool ran unless you received a tool result. Never invent connection status or successes. "
    "After tools return, write a natural final answer (not JSON). High-impact writes need confirmation. "
    "Draft vs Live stay distinct. Live Chat is read-only in V2."
)

def _quick_actions(stage: str | None) -> list[dict[str, str]]:
    base = [
        {"id": "cm", "label": "Review Setup"},
        {"id": "usage", "label": "Check Usage"},
        {"id": "integrations", "label": "Integrations"},
    ]
    if stage in {"new", "cm_partial"}:
        return [{"id": "cm", "label": "Continue Setup"}, *base[1:]]
    return base

def _status_label(name: str) -> str:
    return {
        "read_integrations": "Checking your Instagram/Facebook connection…",
        "diagnose_meta_health": "Reading Meta health evidence…",
        "read_cm": "Reading Content Management…",
        "validate_cm": "Validating your setup…",
        "propose_cm_patch": "Preparing a change proposal…",
        "extract_price_list": "Reading the uploaded price list…",
        "setup_next_step": "Checking setup progress…",
        "get_recent_customer_interactions": "Loading recent customer interactions…",
        "get_interaction_trace": "Reading interaction TRACE…",
        "read_usage": "Checking usage…",
        "help": "Looking up product capabilities…",
    }.get(name, f"Running {name}…")

def _build_messages(
    *,
    context: dict[str, Any],
    user_text: str,
    attachment_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    recent, summary = pack_recent_messages(
        context.get("recent_messages_raw") or context.get("recent_messages"),
        token_budget=owner_context_token_budget() // 3,
    )
    parts = [
        SYSTEM_V2,
        str(context.get("system_prompt") or ""),
        f"Reply language hint: {context.get('reply_language') or 'en'}.",
        f"Account snapshot: {json.dumps(context.get('account_summary') or {}, ensure_ascii=False, default=str)[:2000]}",
    ]
    if context.get("knowledge_block"):
        parts.append(str(context["knowledge_block"]))
    if summary:
        parts.append(summary)
    if attachment_ids:
        parts.append(f"User attached files: {attachment_ids}. Use extract_price_list when appropriate.")
    out: list[dict[str, Any]] = [{"role": "system", "content": "\n".join(p for p in parts if p)}]
    for m in recent:
        out.append({"role": m["role"], "content": m["content"]})
    out.append({"role": "user", "content": user_text})
    return out

def _done_payload(
    *,
    reply_text: str,
    tool_calls: list[dict[str, Any]],
    cards: list[dict[str, Any]],
    choices: list[dict[str, Any]],
    model: str,
    ctx_tokens: int,
    stage: str,
    pending_confirmation: str | None = None,
    proposed_patch: dict[str, Any] | None = None,
    choice_set_id: str | None = None,
    reason: str = "sol_final",
) -> dict[str, Any]:
    return {
        "reply_text": reply_text,
        "tool_calls": tool_calls,
        "cards": cards,
        "choices": choices,
        "choice_set_id": choice_set_id,
        "pending_confirmation": pending_confirmation,
        "proposed_patch": proposed_patch,
        "route": {"kind": "owner_v2", "model": model, "reason": reason},
        "context_tokens": ctx_tokens,
        "setup_stage": stage,
        "quick_actions": _quick_actions(stage),
        "model": model,
    }

async def run_owner_turn_v2(**kwargs: Any) -> OwnerV2TurnResult:
    final: OwnerV2TurnResult | None = None
    async for ev in iter_owner_turn_v2_events(**kwargs):
        if ev.type == "done":
            p = ev.payload
            final = OwnerV2TurnResult(
                reply_text=str(p.get("reply_text") or ""),
                tool_calls=list(p.get("tool_calls") or []),
                cards=list(p.get("cards") or []),
                choices=list(p.get("choices") or []),
                pending_confirmation=p.get("pending_confirmation"),
                proposed_patch=p.get("proposed_patch"),
                route=p.get("route"),
                context_tokens=int(p.get("context_tokens") or 0),
                setup_stage=p.get("setup_stage"),
                quick_actions=list(p.get("quick_actions") or []),
                model=p.get("model"),
            )
        elif ev.type == "cancelled":
            return OwnerV2TurnResult(
                reply_text=str(ev.payload.get("reply_text") or ""),
                cancelled=True,
                model=owner_model_name(),
            )
        elif ev.type == "error" and final is None:
            return OwnerV2TurnResult(
                reply_text=str(ev.payload.get("message") or "Linas AI is temporarily unavailable. Please retry."),
                model=owner_model_name(),
            )
    return final or OwnerV2TurnResult(reply_text="", model=owner_model_name())

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
    is_cancelled: CancelCheck | None = None,
) -> AsyncIterator[StreamEvent]:
    if not owner_copilot_v2_enabled():
        yield StreamEvent(type="error", payload={"message": "OWNER_COPILOT_V2 disabled"})
        return

    text = (user_text or "").strip()
    context = pack_owner_turn_context(
        tenant_id=tenant_id,
        user_id=user_id,
        user_text=text or (confirm_tool or choice_id or ""),
        messages=messages,
    )
    context["recent_messages_raw"] = list(messages or [])
    stage = str((context.get("account_summary") or {}).get("setup_stage") or "")
    reply_lang = str(context.get("reply_language") or "en")
    model = owner_model_name()
    ctx_tokens = max(1, len(json.dumps(context, ensure_ascii=False, default=str)) // 4)

    yield StreamEvent(type="thinking", payload={"label": "Thinking…"})
    if is_cancelled and is_cancelled():
        yield StreamEvent(type="cancelled", payload={"reply_text": ""})
        return

    # Resolve clickable choice
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
            done_payload=_done_payload,
            is_cancelled=is_cancelled,
        ):
            yield ev
        return

    if not text and not (attachment_ids or []):
        msg = "Tell me what you’d like to configure or inspect."
        yield StreamEvent(type="delta", payload={"text": msg})
        yield StreamEvent(type="done", payload=_done_payload(
            reply_text=msg, tool_calls=[], cards=[], choices=[], model=model,
            ctx_tokens=ctx_tokens, stage=stage, reason="empty",
        ))
        return

    if looks_like_creative_request(text):
        msg = creative_refusal_message(language=reply_lang)
        async for piece in _emit_as_deltas(msg):
            yield piece
        yield StreamEvent(type="done", payload=_done_payload(
            reply_text=msg, tool_calls=[], cards=[], choices=[], model=model,
            ctx_tokens=ctx_tokens, stage=stage, reason="creative_cancelled",
        ))
        return

    if attachment_ids:
        tool_args = {**(tool_args or {}), "attachment_id": attachment_ids[0]}

    chat_messages = _build_messages(context=context, user_text=text, attachment_ids=attachment_ids)
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

            response = await sol_chat_completion(messages=chat_messages, tools=OWNER_V2_TOOL_SCHEMAS, stream=False)
            msg = response.choices[0].message
            tcalls = getattr(msg, "tool_calls", None) or []

            if not tcalls:
                reply_text = (getattr(msg, "content", None) or "").strip()
                if reply_text:
                    async for piece in _emit_as_deltas(reply_text):
                        yield piece
                else:
                    reply_parts: list[str] = []
                    async for piece in iter_sol_text_deltas(messages=chat_messages, is_cancelled=is_cancelled):
                        reply_parts.append(piece)
                        yield StreamEvent(type="delta", payload={"text": piece})
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
                    payload=_done_payload(
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
                    ),
                )
                return

            chat_messages.append(
                {
                    "role": "assistant",
                    "content": getattr(msg, "content", None),
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
                yield StreamEvent(type="status", payload={"id": name, "text": _status_label(name)})
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
                chat_messages.append(
                    {"role": "tool", "tool_call_id": tc.id, "content": tool_result_for_model(result)}
                )
                card = card_from_tool(result.name, result.data if isinstance(result.data, dict) else {}, ok=result.ok)
                if card:
                    cards_acc.append(card.to_dict())
                    yield StreamEvent(type="card", payload={"card": card.to_dict()})
                for ch in choices_from_tool_result(result.name, result.data if isinstance(result.data, dict) else {}):
                    choices_acc.append(ch.to_dict())
                if result.name == "propose_cm_patch" and result.ok and isinstance(result.data, dict):
                    proposed_patch = {
                        "proposal_id": result.data.get("proposal_id"),
                        "confirmation_token": result.data.get("confirmation_token"),
                        "preview": result.data.get("preview"),
                    }
                    pending_confirmation = result.confirmation_token

        # Max rounds — stream Sol final over accumulated tool results
        fin_messages = list(chat_messages)
        fin_messages.append(
            {
                "role": "system",
                "content": "Write the natural final owner-facing answer now from the tool results. No JSON.",
            }
        )
        parts: list[str] = []
        async for piece in iter_sol_text_deltas(messages=fin_messages, is_cancelled=is_cancelled):
            parts.append(piece)
            yield StreamEvent(type="delta", payload={"text": piece})
        yield StreamEvent(
            type="done",
            payload=_done_payload(
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

async def _emit_as_deltas(text: str, size: int = 28) -> AsyncIterator[StreamEvent]:
    for i in range(0, len(text or ""), size):
        yield StreamEvent(type="delta", payload={"text": text[i : i + size]})
