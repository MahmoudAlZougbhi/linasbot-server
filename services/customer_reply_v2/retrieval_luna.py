"""Retrieval Luna — selects Published CM evidence; never writes customer replies.

Uses GPT-5.6 Luna only. Final answers are written by Answer Tera separately.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from services.customer_reply_v2.flags import customer_retrieval_model_name, max_retrieval_rounds
from services.customer_reply_v2.manifest import FIXED_ANSWER_SECTIONS, manifest_for_retrieval_luna
from services.customer_reply_v2.models import RetrievalResult
from services.customer_reply_v2.retrieval_tools import RETRIEVAL_TOOL_SCHEMAS, ToolContext, dispatch_retrieval_tool

# Optional injectable for fixtures: async (messages, tools) -> OpenAI-like response
LlmFn = Callable[..., Awaitable[Any]]

_RETRIEVAL_SYSTEM = """You are Retrieval Luna for Linas AI customer automation.
Your only job is to select Published CM evidence using the provided tools.
You NEVER write the customer-visible reply.
You NEVER receive or request full AI Basics or Style bodies — they are fixed Answer context.
Tenant identity is server-side; do not invent tenant IDs.
After reading evidence, respond with a single JSON object (no markdown) containing:
{
  "evidence_status": "sufficient" | "insufficient_can_retry" | "insufficient_final",
  "selected_source_ids": ["section:id", ...],
  "selected_section_ids": ["services", ...],
  "missing_information_category": "",
  "confidence_category": "high|medium|low",
  "multi_intent": false,
  "reason_codes": ["..."]
}
At most two retrieval rounds are allowed. Prefer reading exact items over guessing.
"""


def _strip_fixed_from_prompt(text: str) -> str:
    """Defense-in-depth: never allow full basics/style blobs into retrieval prompts."""
    lowered = text.lower()
    for needle in ("advanced_instructions", "style_body", "identity_summary"):
        if needle in lowered and len(text) > 4000:
            return text[:500] + "…[redacted_fixed_answer_context]"
    return text


async def _default_llm(messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None) -> Any:
    from services.llm_core_service import build_chat_completion_kwargs, client
    from services.model_policy import emit_model_policy_trace, resolve_customer_retrieval_policy

    policy = resolve_customer_retrieval_policy()
    model = customer_retrieval_model_name()
    if model != policy.model:
        raise RuntimeError(
            f"customer_retrieval_model_misconfigured: retrieval model {model!r} != policy {policy.model!r}"
        )
    kwargs = build_chat_completion_kwargs(
        model=model,
        messages=[{"role": "user", "content": "placeholder"}],
        max_tokens=1200,
        temperature=0.2,
        reasoning_effort=str(policy.reasoning_effort),
        has_function_tools=bool(tools),
    )
    kwargs["messages"] = messages
    kwargs["model"] = model
    if tools is not None:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    emit_model_policy_trace(policy, extra={"role": "retrieval", "stage": "retrieval", "has_tools": tools is not None})
    return await client.chat.completions.create(**kwargs)


def _parse_final_plan(content: str) -> dict[str, Any]:
    text = (content or "").strip()
    if not text:
        return {"evidence_status": "insufficient_final", "selected_source_ids": []}
    try:
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:].strip()
        parsed = json.loads(text)
        return (
            parsed if isinstance(parsed, dict) else {"evidence_status": "insufficient_final", "selected_source_ids": []}
        )
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                parsed = json.loads(text[start : end + 1])
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass
    return {"evidence_status": "insufficient_final", "selected_source_ids": [], "parse_error": True}


async def run_retrieval_luna(
    *,
    tenant_id: str,
    message: str,
    customer_profile: dict[str, Any],
    dm_window: list[dict[str, str]] | None = None,
    comment_context: dict[str, Any] | None = None,
    llm_fn: LlmFn | None = None,
    scripted_tool_calls: list[list[dict[str, Any]]] | None = None,
    conversation_id: str | None = None,
    channel: str = "customer",
    reply_to_message_id: str | None = None,
    active_product_id: str | None = None,
) -> RetrievalResult:
    """Run Retrieval Luna with server-enforced max 2 rounds.

    ``scripted_tool_calls`` enables fixture mode: a list of rounds, each a list of
    {name, arguments} tool calls, then a final JSON plan as the last scripted message
    via a trailing dict with key ``final_plan``.
    """
    try:
        model = customer_retrieval_model_name()
    except Exception as exc:
        return RetrievalResult(
            evidence=[],
            evidence_status="insufficient_final",
            rounds_used=0,
            requested_model="",
            returned_model="",
            error=f"retrieval_model_blocker:{exc}",
        )
    try:
        manifest = manifest_for_retrieval_luna(tenant_id)
        revision = str(manifest["published_revision"])
    except Exception as exc:
        return RetrievalResult(
            evidence=[],
            evidence_status="insufficient_final",
            rounds_used=0,
            requested_model=model,
            returned_model="",
            error=str(exc),
        )

    # Prove fixed sections are not selectable content for the model.
    for sec in manifest.get("sections") or []:
        if sec.get("section_id") in FIXED_ANSWER_SECTIONS:
            assert sec.get("fixed_answer_context") is True
            assert sec.get("selectable") is False

    ctx = ToolContext(
        tenant_id=tenant_id,
        published_revision=revision,
        channel=channel,
        customer_profile=customer_profile,
        dm_window=list(dm_window or []),
        comment_context=dict(comment_context or {}),
        conversation_id=conversation_id,
        reply_to_message_id=reply_to_message_id,
        active_product_id=active_product_id,
    )

    if reply_to_message_id and conversation_id:
        from db.session import whatsapp_session
        from services.products.crv2_tools import crv2_resolve_reply_to_product

        try:
            with whatsapp_session(require=True) as db:
                reply_hit = crv2_resolve_reply_to_product(
                    db,
                    tenant_id=tenant_id,
                    channel=channel,
                    reply_to_message_id=reply_to_message_id,
                    conversation_id=conversation_id,
                )
                match = reply_hit.get("match")
                if match:
                    ctx.active_product_id = str(match.get("id") or "") or None
        except Exception:
            pass

    if not ctx.active_product_id and conversation_id:
        from db.session import whatsapp_session
        from services.products.active_context import get_active_product

        try:
            with whatsapp_session(require=True) as db:
                active = get_active_product(db, tenant_id=tenant_id, conversation_id=conversation_id)
                if active:
                    ctx.active_product_id = str(active.get("active_product_id") or "") or None
        except Exception:
            pass

    if scripted_tool_calls is not None:
        return await _run_scripted(ctx, scripted_tool_calls, model=model)

    llm = llm_fn or _default_llm
    user_payload = {
        "current_message": _strip_fixed_from_prompt(message),
        "manifest": manifest,
        "customer_facts": customer_profile,
        "dm_window_preview": list(dm_window or [])[-6:],
        "comment_context_preview": {
            k: comment_context.get(k)
            for k in (
                "media_type",
                "caption",
                "parent_comment",
                "media_status",
                "permalink",
            )
            if comment_context and k in comment_context
        },
        "note": "Use tools to list/read selectable sections only. Do not write the reply.",
    }
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _RETRIEVAL_SYSTEM},
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
    ]

    returned_model = model
    max_loops = max_retrieval_rounds() * 4  # tool micro-steps inside rounds
    final_plan: dict[str, Any] = {}

    for _ in range(max_loops):
        response = await llm(messages=messages, tools=RETRIEVAL_TOOL_SCHEMAS)
        returned_model = getattr(response, "model", None) or model
        msg = response.choices[0].message
        tcalls = getattr(msg, "tool_calls", None) or []
        if not tcalls:
            final_plan = _parse_final_plan(getattr(msg, "content", None) or "")
            break
        messages.append(
            {
                "role": "assistant",
                "content": getattr(msg, "content", None),
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments or "{}"},
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
            # Round gate for additional requests
            if name == "request_additional_published_cm_items" and ctx.round_index >= max_retrieval_rounds():
                result = {
                    "ok": False,
                    "error": "retrieval_round_limit",
                    "message": f"Server refuses retrieval beyond {max_retrieval_rounds()} rounds.",
                }
                ctx.refused_third_round = True
                ctx.audit.append({"tool": name, "ok": False, "class": "round_limit"})
            else:
                result = dispatch_retrieval_tool(name, args, ctx)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result, ensure_ascii=False)})
        if ctx.refused_third_round:
            final_plan = {
                "evidence_status": "insufficient_final" if not ctx.evidence_acc else "sufficient",
                "selected_source_ids": [e.source_id for e in ctx.evidence_acc],
                "reason_codes": ["round_limit_enforced"],
            }
            break
    else:
        final_plan = {
            "evidence_status": "insufficient_final",
            "selected_source_ids": [e.source_id for e in ctx.evidence_acc],
            "reason_codes": ["loop_exhausted"],
        }

    status = str(final_plan.get("evidence_status") or "insufficient_final")
    if status == "insufficient_can_retry" and ctx.round_index >= max_retrieval_rounds():
        status = "insufficient_final"
    if status not in {"sufficient", "insufficient_can_retry", "insufficient_final"}:
        status = "insufficient_final"

    selected = list(final_plan.get("selected_source_ids") or [e.source_id for e in ctx.evidence_acc])
    sections = list(final_plan.get("selected_section_ids") or sorted({e.section_id for e in ctx.evidence_acc}))

    return RetrievalResult(
        evidence=list(ctx.evidence_acc),
        evidence_status=status,  # type: ignore[arg-type]
        rounds_used=ctx.round_index,
        selected_section_ids=sections,
        selected_source_ids=selected,
        tool_trace=list(ctx.audit),
        requested_model=model,
        returned_model=str(returned_model),
        refused_third_round=ctx.refused_third_round,
    )


async def _run_scripted(
    ctx: ToolContext,
    scripted: list[Any],
    *,
    model: str,
) -> RetrievalResult:
    final_plan: dict[str, Any] = {"evidence_status": "insufficient_final", "selected_source_ids": []}
    for step in scripted:
        if isinstance(step, dict) and "final_plan" in step:
            final_plan = dict(step["final_plan"])
            continue
        if not isinstance(step, list):
            continue
        for call in step:
            name = str(call.get("name") or "")
            args = dict(call.get("arguments") or {})
            if name == "request_additional_published_cm_items" and ctx.round_index >= max_retrieval_rounds():
                ctx.refused_third_round = True
                ctx.audit.append({"tool": name, "ok": False, "class": "round_limit"})
                continue
            dispatch_retrieval_tool(name, args, ctx)

    status = str(final_plan.get("evidence_status") or "insufficient_final")
    if status == "insufficient_can_retry" and ctx.round_index >= max_retrieval_rounds():
        status = "insufficient_final"
    selected = list(final_plan.get("selected_source_ids") or [e.source_id for e in ctx.evidence_acc])
    sections = list(final_plan.get("selected_section_ids") or sorted({e.section_id for e in ctx.evidence_acc}))
    return RetrievalResult(
        evidence=list(ctx.evidence_acc),
        evidence_status=status,  # type: ignore[arg-type]
        rounds_used=ctx.round_index,
        selected_section_ids=sections,
        selected_source_ids=selected,
        tool_trace=list(ctx.audit),
        requested_model=model,
        returned_model=model,
        refused_third_round=ctx.refused_third_round,
    )


def retrieval_prompt_contains_full_basics_or_style(system_and_user: str) -> bool:
    """Test helper: Retrieval prompts must not embed full AI Basics/Style bodies."""
    markers = ("advanced_instructions", "style_body", "do_list", "dont_list")
    # Manifest descriptions mentioning the words are OK; full bodies are large.
    return any(m in system_and_user for m in markers) and len(system_and_user) > 8000
