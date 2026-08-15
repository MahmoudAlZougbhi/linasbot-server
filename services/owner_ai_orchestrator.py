"""Owner Linas AI System Copilot turn orchestration with compact context + safe tools."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from services.owner_ai_context import estimate_context_tokens, pack_owner_turn_context
from services.owner_ai_model_router import (
    decision_to_dict,
    owner_chat_usage_tracker,
    route_owner_turn,
)
from services.owner_ai_tools import dispatch_tool
from services.system_knowledge_retrieval import help_payload_for_query


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
    # V2 extras (populated when OWNER_COPILOT_V2 path runs).
    cards: list[dict[str, Any]] = field(default_factory=list)
    choices: list[dict[str, Any]] = field(default_factory=list)
    model: str | None = None


_INTENT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(what can you do|capabilities|help|ماذا تستطيع|aide)\b", re.I), "help"),
    (re.compile(r"\b(usage|credits|wallet|how much|الاستخدام|crédits)\b", re.I), "read_usage"),
    (re.compile(r"\b(subscription|plan|billing|الاشتراك|abonnement)\b", re.I), "read_subscription"),
    (
        re.compile(
            r"("
            r"create(\s+a)?\s+post|make(\s+a)?\s+post|"
            r"draft(\s+a)?\s+(caption|post)|"
            r"write(\s+a)?\s+(caption|post)|"
            r"generate(\s+a)?\s+(caption|post|image)|"
            r"creative\s+studio|compress(\s+this|\s+the)?\b|"
            r"بدي\s*(نعمل|اعمل|أعمل)\s*(بوست|منشور)|"
            r"بدنا\s*(نعمل|ننشئ)\s*(بوست|منشور)|"
            r"أريد\s*(أن\s*)?(أعمل|انشئ|أنشئ)\s*(بوست|منشور)|"
            r"انشاء\s*منشور|اعمل\s*(بوست|منشور)|"
            r"créer(\s+une)?\s+(publication|post)"
            r")",
            re.I,
        ),
        "create_creative_draft",
    ),
    (re.compile(r"\b(instagram|facebook|meta|integrat|connected|ربط)\b", re.I), "read_integrations"),
    (re.compile(r"\b(validate|missing|setup complete|تحقق)\b", re.I), "validate_cm"),
    (re.compile(r"\b(publish|انشر|publier)\b", re.I), "publish_cm"),
    (re.compile(r"\b(what does my ai know|content management|\bcm\b|إعداد)\b", re.I), "read_cm"),
    (re.compile(r"\b(dashboard|metrics|stats|لوحة)\b", re.I), "read_dashboard_metrics"),
    (re.compile(r"\b(scheduled|schedule|مجدول)\b", re.I), "read_scheduled_posts"),
    (re.compile(r"\b(jobs|errors|queue|worker)\b", re.I), "read_jobs_errors"),
    (re.compile(r"\b(my profile|who am i|address me|ملفي)\b", re.I), "read_profile"),
    (re.compile(r"\b(account summary|status|أين وصلنا)\b", re.I), "read_account_summary"),
    (
        re.compile(
            r"\b(bad reply|wrong answer|diagnos|why did|incorrect|خطأ|تشخيص|mauvaise réponse)\b",
            re.I,
        ),
        "get_recent_customer_interactions",
    ),
    (
        re.compile(r"\b(faq quota|smart answers?|faq limit|حصة|réponses intelligentes)\b", re.I),
        "read_faq_quota",
    ),
    (
        re.compile(r"\b(save smart answer|add faq|حفظ إجابة|enregistrer faq)\b", re.I),
        "propose_smart_answer",
    ),
]


def _quick_actions(stage: str | None) -> list[dict[str, str]]:
    base = [
        {"id": "cm", "label": "Review Setup"},
        {"id": "usage", "label": "Check Usage"},
        {"id": "create", "label": "Create Post"},
    ]
    if stage in {"new", "cm_partial"}:
        return [{"id": "cm", "label": "Continue Setup"}, {"id": "integrations", "label": "Integrations"}, *base[1:]]
    if stage == "cm_ready_no_integration":
        return [{"id": "integrations", "label": "Connect Meta"}, *base]
    return base


def _summarize(name: str, result_data: dict[str, Any], *, reply_language: str) -> str:
    if name == "help":
        caps = result_data.get("capabilities") or []
        titles = [str(c.get("feature")) for c in caps if isinstance(c, dict)][:6]
        if reply_language == "ar":
            return "يمكنني المساعدة في: " + ("، ".join(titles) if titles else "إعداد النظام والاستخدام والتكاملات.")
        if reply_language == "fr":
            return "Je peux aider pour: " + (", ".join(titles) if titles else "configuration, usage, intégrations.")
        return (
            "I’m your System Copilot. CM setup is one capability — I also cover integrations, "
            f"usage, billing, creative, and ops. Relevant now: {', '.join(titles) or 'general help'}."
        )
    if name == "read_usage":
        return f"Usage snapshot: {result_data.get('wallet')}"
    if name == "read_subscription":
        return f"Subscription: {result_data}"
    if name == "read_integrations":
        return f"Integrations: {result_data.get('integrations')}"
    if name == "validate_cm":
        report = result_data.get("report") or {}
        errors = report.get("errors") if isinstance(report, dict) else None
        return f"Validation complete. Errors: {len(errors) if isinstance(errors, list) else 'see report'}."
    if name == "publish_cm":
        return "Publish completed successfully."
    if name == "approve_cm_patch":
        activation = result_data.get("activation") or {}
        if activation.get("activated") or result_data.get("live"):
            return (
                f"CM patch is Live for customer replies and validated: {result_data.get('validation')}. "
                "No separate Publish step is required after approval."
            )
        reason = activation.get("reason") or "activation_failed"
        return (
            f"CM patch saved to draft and validated: {result_data.get('validation')}. "
            f"Live publish did not complete ({reason}"
            f"{': ' + str(activation.get('message')) if activation.get('message') else ''}). "
            "Do not claim customers already see this change."
        )
    if name == "propose_cm_patch":
        preview = result_data.get("preview") or {}
        return (
            "Proposed AI Setup change ready for your review "
            f"(section={preview.get('section')}, keys={preview.get('changed_keys')}). "
            "Tap Approve or reply ok / موافق / yes to apply it Live for customer replies."
        )
    if name == "get_recent_customer_interactions":
        return (
            f"Found {result_data.get('count', 0)} recent customer interactions. "
            "Pick one to diagnose (share the trace id) or say what went wrong."
        )
    if name == "get_interaction_trace":
        diag = result_data.get("diagnosis") or {}
        return (
            f"Root cause: {diag.get('root_cause')}. {diag.get('explanation')} "
            "I can propose a correction for your approval."
        )
    if name == "propose_diagnosis_fix":
        return "Proposed diagnosis fix ready for approval. Confirm to apply immediately (no Publish step)."
    if name == "approve_diagnosis_fix":
        return f"Diagnosis fix applied: {result_data.get('applied')}"
    if name == "read_faq_quota":
        ent = result_data.get("entitlement") or {}
        return f"Smart Q&A quota: {ent.get('quota_display')} (enabled={ent.get('faq_enabled')})."
    if name == "propose_smart_answer":
        return "Proposed Smart Q&A ready for approval."
    if name == "approve_smart_answer":
        live = bool(result_data.get("live"))
        gid = result_data.get("qa_group_id")
        if live:
            return f"Smart Q&A saved and Live for customers (qa_group_id={gid})."
        reason = ((result_data.get("activation") or {}) if isinstance(result_data.get("activation"), dict) else {}).get(
            "reason"
        )
        return f"Smart Q&A saved as draft (qa_group_id={gid})" + (
            f"; Live not updated yet ({reason})." if reason else "."
        )
    if name == "read_cm":
        if "sections" in result_data:
            return (
                f"AI Setup: {result_data.get('sections_present')}/"
                f"{result_data.get('sections_total')} sections present; "
                f"published={result_data.get('published')}."
            )
        return f"CM section snapshot: {result_data.get('section')} keys={((result_data.get('draft') or {}).get('payload_keys'))}"
    if name == "read_profile":
        return f"Profile: {result_data.get('profile')}"
    if name == "read_account_summary":
        return (
            f"Account stage={result_data.get('setup_stage')}; "
            f"CM={result_data.get('cm')}; integrations={result_data.get('integrations')}."
        )
    if name == "read_dashboard_metrics":
        return f"Dashboard summary: {result_data.get('setup_signals')} wallet={result_data.get('wallet')}"
    if name == "read_scheduled_posts":
        return f"Scheduled posts: {result_data.get('count', 0)}"
    if name == "read_jobs_errors":
        if not result_data.get("available"):
            return f"Jobs/errors: {result_data.get('reason')}"
        return f"Jobs/errors stats: {result_data.get('stats')}"
    if name == "update_profile":
        return f"Profile updated: {result_data.get('profile')}"
    if name == "create_creative_draft":
        status = result_data.get("status")
        if status == "needs_brief":
            if reply_language == "ar":
                return (
                    "تمام — خلّينا نعمل بوست من هون بالشات. "
                    "اختَر نوع المهمة (Auto / Compress / Caption / Post / Image) "
                    "أو اكتبلي شو بدك بالمنشور."
                )
            if reply_language == "fr":
                return (
                    "Parfait — créons la publication ici dans le chat. "
                    "Choisis Auto / Compress / Caption / Post / Image, ou décris le contenu."
                )
            return (
                "Let’s create that in chat. Pick Auto / Compress / Caption / Post / Image, "
                "or describe what the post should say."
            )
        if status == "unavailable":
            return str(result_data.get("reason") or "That creative kind is not available yet.")
        if status == "queued":
            return f"Creative {result_data.get('kind')} job queued ({result_data.get('job_id')})."
        if status == "completed":
            text = str(result_data.get("text") or "").strip()
            preview = text if len(text) <= 480 else text[:477] + "…"
            return f"Draft ready ({result_data.get('kind')}):\n\n{preview}"
        return "Creative draft updated."
    if name == "schedule_creative_draft":
        return (
            f"Scheduled on {result_data.get('platform')} for {result_data.get('scheduled_at')}. "
            f"{result_data.get('note') or ''}"
        ).strip()
    return "Done."


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
    from services.owner_copilot_v2.flags import owner_copilot_v2_enabled

    if ai_generation_blocked(tenant_id):
        paused = owner_credits_paused_payload(tenant_id)
        return OwnerTurnResult(reply_text="", route={"reason": "insufficient_credits", **paused})

    if owner_copilot_v2_enabled():
        from services.owner_copilot_v2.brain_run import run_owner_turn_v2

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
        # Preserve OwnerTurnResult shape; creative always None under V2.
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

    text = (user_text or "").strip()
    context = pack_owner_turn_context(
        tenant_id=tenant_id,
        user_id=user_id,
        user_text=text or (confirm_tool or ""),
        messages=messages,
    )
    ctx_tokens = estimate_context_tokens(context)
    stage = str((context.get("account_summary") or {}).get("setup_stage") or "")
    reply_lang = str(context.get("reply_language") or "en")

    if not text and not confirm_tool:
        return OwnerTurnResult(
            reply_text="Tell me what you’d like to configure or inspect.",
            context_tokens=ctx_tokens,
            setup_stage=stage,
            quick_actions=_quick_actions(stage),
        )

    intent: str | None = None
    args: dict[str, Any] = dict(tool_args or {})
    confirmed = False

    if confirm_tool:
        if confirm_tool.startswith("approve_cm_patch:"):
            intent = "approve_cm_patch"
            args["proposal_id"] = confirm_tool.split(":", 1)[1]
            confirmed = True
        elif confirm_tool.startswith("approve_diagnosis_fix:"):
            intent = "approve_diagnosis_fix"
            args["proposal_id"] = confirm_tool.split(":", 1)[1]
            confirmed = True
        elif confirm_tool.startswith("approve_smart_answer:"):
            intent = "approve_smart_answer"
            args["proposal_id"] = confirm_tool.split(":", 1)[1]
            confirmed = True
        else:
            intent = confirm_tool
            confirmed = True

    if not intent:
        for pattern, name in _INTENT_PATTERNS:
            if pattern.search(text):
                intent = name
                break

    # Client create-post mode: chip selection forces creative tool without NL match.
    if not intent and (args.get("creative_kind") or args.get("kind")):
        intent = "create_creative_draft"

    if intent == "create_creative_draft":
        args.setdefault("prompt", text)
        if args.get("creative_kind") and not args.get("kind"):
            args["kind"] = args.get("creative_kind")

    route = route_owner_turn(text, intent=intent)
    if ctx_tokens > route.max_context_tokens:
        # Compact further: drop conversation summary if over budget (truthful, no invent).
        context = {**context, "conversation_summary": None, "recent_messages": context.get("recent_messages", [])[-4:]}
        ctx_tokens = estimate_context_tokens(context)

    # Conversational help (no tool writes): real LLM + knowledge + recent history.
    # Operational intents keep the existing tool dispatch path.
    if intent is None or intent == "help":
        from services.owner_ai_natural_reply import OwnerAIModelError, generate_owner_conversational_reply

        help_data = help_payload_for_query(text if intent is None else str(args.get("query") or text))
        try:
            reply_text = await generate_owner_conversational_reply(
                user_text=text,
                context=context,
                help_data=help_data,
            )
        except OwnerAIModelError as exc:
            owner_chat_usage_tracker.record(
                tenant_id=tenant_id,
                user_id=user_id,
                conversation_id=conversation_id,
                route=route,
                prompt_tokens=ctx_tokens,
                completion_tokens=1,
                meta={"intent": intent or "help_fallback", "ok": False, "error": str(exc)},
            )
            return OwnerTurnResult(
                reply_text=(f"Linas AI is temporarily unavailable to answer that. Please try again shortly ({exc})."),
                tool_calls=[{"ok": False, "name": "help", "data": help_data, "requires_confirmation": False}],
                route=decision_to_dict(route),
                context_tokens=ctx_tokens,
                setup_stage=stage,
                quick_actions=_quick_actions(stage),
            )

        owner_chat_usage_tracker.record(
            tenant_id=tenant_id,
            user_id=user_id,
            conversation_id=conversation_id,
            route=route,
            prompt_tokens=ctx_tokens,
            completion_tokens=max(1, len(reply_text) // 4),
            meta={"intent": intent or "help_fallback", "ok": True, "llm": True},
        )
        return OwnerTurnResult(
            reply_text=reply_text,
            tool_calls=[{"ok": True, "name": "help", "data": help_data, "requires_confirmation": False}],
            route=decision_to_dict(route),
            context_tokens=ctx_tokens,
            setup_stage=stage,
            quick_actions=_quick_actions(stage),
        )

    try:
        tool_result = await dispatch_tool(
            intent,
            tenant_id=tenant_id,
            user_id=user_id,
            role=role,
            args=args,
            confirmed=confirmed,
        )
    except PermissionError as exc:
        return OwnerTurnResult(
            reply_text=f"I can’t do that with your role: {exc}",
            route=decision_to_dict(route),
            context_tokens=ctx_tokens,
            setup_stage=stage,
            quick_actions=_quick_actions(stage),
        )
    except Exception as exc:
        return OwnerTurnResult(
            reply_text=f"That tool failed safely without applying changes: {type(exc).__name__}",
            route=decision_to_dict(route),
            context_tokens=ctx_tokens,
            setup_stage=stage,
            quick_actions=_quick_actions(stage),
        )

    tool_payload = tool_result.to_dict()
    owner_chat_usage_tracker.record(
        tenant_id=tenant_id,
        user_id=user_id,
        conversation_id=conversation_id,
        route=route,
        prompt_tokens=ctx_tokens,
        completion_tokens=max(1, len(tool_result.error or "") // 4 + len(str(tool_result.data)) // 8),
        meta={"intent": intent, "ok": tool_result.ok},
    )

    proposed = None
    if tool_result.name == "propose_cm_patch" and isinstance(tool_result.data, dict):
        proposed = {
            "proposal_id": tool_result.data.get("proposal_id"),
            "confirmation_token": tool_result.data.get("confirmation_token"),
            "preview": tool_result.data.get("preview"),
        }

    creative = None
    if tool_result.name in {"create_creative_draft", "schedule_creative_draft"} and isinstance(tool_result.data, dict):
        creative = dict(tool_result.data)

    if tool_result.requires_confirmation:
        return OwnerTurnResult(
            reply_text=_summarize(tool_result.name, tool_result.data, reply_language=reply_lang)
            if tool_result.name == "propose_cm_patch"
            else (f"This is a high-impact action. Confirm in the app to proceed ({tool_result.confirmation_token})."),
            tool_calls=[tool_payload],
            pending_confirmation=tool_result.confirmation_token,
            proposed_patch=proposed,
            creative_draft=creative,
            route=decision_to_dict(route),
            context_tokens=ctx_tokens,
            setup_stage=stage,
            quick_actions=_quick_actions(stage),
        )

    if not tool_result.ok:
        return OwnerTurnResult(
            reply_text=tool_result.error or "Tool failed.",
            tool_calls=[tool_payload],
            creative_draft=creative,
            route=decision_to_dict(route),
            context_tokens=ctx_tokens,
            setup_stage=stage,
            quick_actions=_quick_actions(stage),
        )

    return OwnerTurnResult(
        reply_text=_summarize(tool_result.name, tool_result.data, reply_language=reply_lang),
        tool_calls=[tool_payload],
        proposed_patch=proposed,
        creative_draft=creative,
        route=decision_to_dict(route),
        context_tokens=ctx_tokens,
        setup_stage=stage,
        quick_actions=_quick_actions(stage),
    )
