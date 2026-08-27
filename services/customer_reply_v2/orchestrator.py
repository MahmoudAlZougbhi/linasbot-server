"""Customer Reply AI V2 orchestrator — DM and comment runtimes (production sole engine)."""

from __future__ import annotations

import time
from typing import Any

from services.cm.version_store import PublishedVersionError
from services.customer_reply_v2.channel_metadata import build_channel_metadata
from services.customer_reply_v2.conversation_window import load_dm_conversation_window
from services.customer_reply_v2.customer_facts import apply_message_fact_updates, load_customer_facts
from services.customer_reply_v2.flags import (
    customer_ai_v10_runtime_enabled,
    customer_answer_model_name,
    customer_retrieval_model_name,
    customer_semantic_retrieval_enabled,
    dm_context_window_minutes,
    flags_snapshot,
)
from services.customer_reply_v2.history_format import history_records_from_window, same_history_for_agents
from services.customer_reply_v2.invocation_meter import CustomerTurnMeter, InvocationRecord
from services.customer_reply_v2.manifest import get_cached_manifest, load_fixed_answer_context
from services.customer_reply_v2.models import CustomerReplyOutcome
from services.customer_reply_v2.observability import build_safe_trace
from services.customer_reply_v2.orchestrator_faq import evaluate_faq_turn, faq_direct_outcome_kwargs, faq_trace_fields
from services.customer_reply_v2.orchestrator_llm import run_dm_luna_then_tera
from services.customer_reply_v2.orchestrator_side_effects import plan_turn_side_effects
from services.customer_reply_v2.orchestrator_validate import safe_failure_reply
from services.customer_reply_v2.policy import enforce_restricted_and_handoff
from services.customer_reply_v2.safety_gate import evaluate_customer_safety


async def run_customer_reply_v2_dm(
    *,
    tenant_id: str,
    message: str,
    detected_language: str = "",
    response_language: str = "",
    channel: str = "instagram_dm",
    asset_id: str = "",
    provider_sender_id: str = "",
    provider_display_name: str = "",
    user_id: str = "",
    conversation_id: str = "",
    reply_to_message_id: str = "",
    message_id: str = "",
    attachment_types: list[str] | None = None,
    inbound_media: dict[str, Any] | None = None,
    injected_history: list[dict[str, Any]] | None = None,
    scripted_retrieval: list[Any] | None = None,
    fixture_answer: dict[str, Any] | None = None,
    now_ts: float | None = None,
    apply_customer_usage_limits: bool = True,
) -> CustomerReplyOutcome:
    """Canonical DM flow for Customer Reply AI V2 (sole production engine)."""
    started = time.perf_counter()
    word_notice: str | None = None

    from services.credit_ai_gate import ai_generation_blocked

    if ai_generation_blocked(tenant_id, honor_inflight_reserved=True):
        return CustomerReplyOutcome(
            stop=True,
            reply=None,
            reason="insufficient_credits",
            evidence_status="policy_stop",
            metadata={"ai_called": False, "cost_status": "none", "flags": flags_snapshot()},
        )

    def _out(**kwargs: Any) -> CustomerReplyOutcome:
        outcome = CustomerReplyOutcome(**kwargs)
        if word_notice:
            body = (outcome.reply or "").strip()
            outcome.reply = f"{word_notice}\n\n{body}".strip() if body else word_notice
        return outcome

    from services.cm.language_policy import ensure_customer_languages

    detected_language, response_language = ensure_customer_languages(
        tenant_id=tenant_id,
        message=message,
        detected_language=detected_language,
        response_language=response_language,
        conversation_id=conversation_id or None,
    )

    try:
        revision, _manifest = get_cached_manifest(tenant_id)
    except PublishedVersionError:
        return _out(
            stop=True,
            reply=safe_failure_reply(response_language, kind="insufficient"),
            reason="no_published_version",
            evidence_status="insufficient_final",
            metadata={"classic_fallback": False, "flags": flags_snapshot()},
            error="no_published_version",
        )

    if apply_customer_usage_limits:
        from services.ai_limits_enforcement import (
            apply_inbound_word_limit,
            customer_reply_limit_message,
            enforce_text_reply_quota,
        )

        limit_user = {
            "tenant_id": tenant_id,
            "social_sender_id": provider_sender_id or user_id,
            "user_preferred_lang": response_language,
        }
        message, word_notice = apply_inbound_word_limit(
            user_id=user_id or provider_sender_id or "unknown",
            user_data=limit_user,
            text=message,
        )
        reply_quota = enforce_text_reply_quota(
            user_id=user_id or provider_sender_id or "unknown",
            user_data=limit_user,
            consume=True,
        )
        if not reply_quota.allowed:
            return _out(
                stop=True,
                reply=customer_reply_limit_message(reply_quota),
                reason=reply_quota.reason or "ai_reply_limit",
                evidence_status="policy_stop",
                metadata={
                    "ai_limits": reply_quota.to_public_dict(),
                    "flags": flags_snapshot(),
                    "ai_called": False,
                    "cost_status": "none",
                },
            )

    facts = load_customer_facts(
        tenant_id=tenant_id,
        channel=channel,
        asset_id=asset_id or "default",
        provider_sender_id=provider_sender_id or user_id or "unknown",
        provider_display_name=provider_display_name,
    )
    facts = apply_message_fact_updates(facts, message, detected_language)
    profile = facts.to_safe_dict()
    meter = CustomerTurnMeter(tenant_id=tenant_id)
    inbound = dict(inbound_media or {})
    if inbound and not attachment_types:
        attachment_types = [str(t) for t in (inbound.get("attachment_types") or []) if str(t).strip()]
    channel_meta = build_channel_metadata(
        channel=channel,
        account_id=asset_id,
        message_id=message_id,
        conversation_id=conversation_id,
        reply_to=reply_to_message_id or None,
        inbound_media=inbound or None,
    )
    v10 = customer_ai_v10_runtime_enabled()
    if v10:
        safety = await evaluate_customer_safety(
            tenant_id=tenant_id,
            text=message,
            channel=channel,
            user_id=provider_sender_id or user_id or None,
            response_language=response_language,
            is_public=bool(channel_meta["is_public"]),
            attachment_types=attachment_types,
            image_urls=list(inbound.get("safety_image_urls") or []),
        )
        if safety.blocked:
            meter.record(
                InvocationRecord(
                    operation="moderation",
                    requested_reasoning_effort=None,
                    effective_reasoning_effort=None,
                    success=True,
                    is_ai=False,
                    failure_stage="safety_block",
                )
            )
            return _out(
                stop=True,
                reply=safety.reply,
                reason="safety_block",
                evidence_status="policy_stop",
                metadata={
                    "ai_called": False,
                    "cost_status": "none",
                    "safety_result": safety.certainty,
                    "safety_policy_version": safety.policy_version,
                    "safety_reasons": safety.reasons,
                    "channel_metadata": channel_meta,
                    "metering": meter.to_public_dict(),
                    "flags": flags_snapshot(),
                },
            )

    policy = enforce_restricted_and_handoff(
        tenant_id=tenant_id,
        message=message,
        response_language=response_language,
        explicit_gender=facts.gender,
        channel=channel,
    )
    if policy:
        trace = build_safe_trace(
            tenant_id=tenant_id,
            channel=channel,
            published_revision=revision,
            faq_category="skipped_policy",
            retrieval_rounds=0,
            selected_source_ids=[],
            evidence_status="policy_stop",
            validation_ok=True,
            repair_attempts=0,
            requested_models={},
            returned_models={},
            context_message_count=0,
            context_compacted=False,
            delivery_result="policy_reply",
            latency_ms=(time.perf_counter() - started) * 1000,
            stage="policy",
        )
        return _out(
            stop=True,
            reply=policy["reply"],
            reason=policy["reason"],
            evidence_status="policy_stop",
            metadata={**policy.get("metadata", {}), "trace": trace, "flags": flags_snapshot()},
        )

    window = await load_dm_conversation_window(
        user_id=user_id or provider_sender_id,
        conversation_id=conversation_id or "dm",
        injected_messages=injected_history,
        now_ts=now_ts,
    )
    history_msgs = window.as_openai_messages()
    if history_msgs and history_msgs[-1].get("role") == "user" and history_msgs[-1].get("content") == message:
        history_for_model = history_msgs[:-1]
    else:
        history_for_model = history_msgs
    shared_history = same_history_for_agents(history_records_from_window(window, channel=channel))
    if shared_history and shared_history[-1].get("sender") == "customer" and shared_history[-1].get("text") == message:
        shared_history = shared_history[:-1]
    if v10:
        luna_history = shared_history
        tera_history = shared_history
    else:
        luna_history = [{"role": m["role"], "content": m["content"]} for m in history_for_model][-6:]
        tera_history = [{"role": m["role"], "content": m["content"]} for m in history_for_model]

    faq = await evaluate_faq_turn(
        tenant_id=tenant_id,
        message=message,
        detected_language=detected_language,
        response_language=response_language,
        channel=channel,
        customer_id=provider_sender_id or user_id,
        attachment_types=attachment_types,
        reply_to=reply_to_message_id,
    )
    if faq.hit:
        return _out(
            **faq_direct_outcome_kwargs(
                tenant_id=tenant_id,
                channel=channel,
                revision=revision,
                faq=faq,
                started=started,
                meter=meter,
                context_message_count=len(window.messages),
                context_compacted=window.context_compacted,
                extra_metadata={"channel_metadata": channel_meta},
            )
        )

    if not customer_semantic_retrieval_enabled():
        return _out(
            stop=True,
            reply=safe_failure_reply(response_language, kind="model"),
            reason="semantic_retrieval_disabled",
            error="CUSTOMER_SEMANTIC_RETRIEVAL_ENABLED=false",
            evidence_status="insufficient_final",
            metadata={"flags": flags_snapshot(), "blocker": "semantic_retrieval_disabled"},
        )

    try:
        customer_retrieval_model_name()
        customer_answer_model_name()
    except Exception as exc:
        return _out(
            stop=True,
            reply=safe_failure_reply(response_language, kind="model"),
            reason="model_misconfigured",
            error=str(exc),
            evidence_status="insufficient_final",
            metadata={"flags": flags_snapshot(), "blocker": str(exc)},
        )
    retrieval, answer, llm_extra = await run_dm_luna_then_tera(
            tenant_id=tenant_id,
            message=message,
            profile=profile,
            luna_history=luna_history,
            tera_history=tera_history,
            scripted_retrieval=scripted_retrieval,
            conversation_id=conversation_id,
            channel=channel,
            reply_to_message_id=reply_to_message_id,
            channel_meta=channel_meta,
            faq_candidates=faq.evidence_candidates,
            provider_sender_id=provider_sender_id,
            user_id=user_id,
            asset_id=asset_id,
            response_language=response_language,
            detected_language=detected_language,
            fixture_answer=fixture_answer,
            meter=meter,
        )
    if llm_extra.get("blocker"):
        return _out(
            stop=True,
            reply=safe_failure_reply(response_language, kind="model"),
            reason="retrieval_model_blocker",
            error=str(llm_extra["blocker"]),
            evidence_status="insufficient_final",
            metadata={"flags": flags_snapshot(), "blocker": llm_extra["blocker"]},
        )
    assert retrieval is not None and answer is not None
    reply_text = str(llm_extra.get("reply_text") or "")
    prompt_tokens = int(llm_extra.get("prompt_tokens") or 0)
    completion_tokens = int(llm_extra.get("completion_tokens") or 0)
    repair_attempts = int(llm_extra.get("repair_attempts") or 0)
    validation_ok = bool(llm_extra.get("validation_ok", True))
    failed_rules = list(llm_extra.get("failed_rules") or [])
    stages_ms = dict(llm_extra.get("stages_ms") or {})

    # Prove fixed answer context was loaded for generated path
    fixed = load_fixed_answer_context(tenant_id)
    assert "ai_basics" in fixed and "style" in fixed

    total_tokens = prompt_tokens + completion_tokens
    side_meta = plan_turn_side_effects(
        tenant_id=tenant_id,
        customer_id=provider_sender_id or user_id,
        conversation_id=conversation_id,
        channel=channel,
        answer=answer,
        channel_metadata=channel_meta,
        meter=meter,
        idempotency_key=meter.customer_turn_id,
        allowed_source_ids=list(retrieval.selected_source_ids or []),
    )
    trace = build_safe_trace(
        tenant_id=tenant_id,
        channel=channel,
        published_revision=revision,
        faq_category=faq.reason or "faq_miss",
        retrieval_rounds=retrieval.rounds_used,
        selected_source_ids=retrieval.selected_source_ids,
        evidence_status=str(retrieval.evidence_status),
        validation_ok=validation_ok,
        repair_attempts=repair_attempts,
        requested_models={
            "retrieval": retrieval.requested_model or "",
            "answer": answer.requested_model or "",
        },
        returned_models={
            "retrieval": retrieval.returned_model,
            "answer": answer.returned_model,
        },
        context_message_count=len(window.messages),
        context_compacted=window.context_compacted,
        delivery_result="ready_to_send",
        latency_ms=(time.perf_counter() - started) * 1000,
        stage="repair" if repair_attempts else "answer",
        reasoning_effort={
            "retrieval_requested": getattr(retrieval, "requested_reasoning_effort", None) or "none",
            "retrieval_effective": getattr(retrieval, "effective_reasoning_effort", None) or "none",
            "answer_requested": getattr(answer, "requested_reasoning_effort", None) or answer.reasoning_effort,
            "answer_effective": getattr(answer, "effective_reasoning_effort", None) or answer.reasoning_effort,
        },
        prompt_tokens=prompt_tokens or None,
        completion_tokens=completion_tokens or None,
        total_tokens=total_tokens or None,
        faq_checked=True,
        faq_match_id=str((faq.metadata or {}).get("faq_id") or ""),
        faq_match_score=(faq.metadata or {}).get("match_score"),
        faq_direct_reply=False,
    )

    return _out(
        stop=True,
        reply=reply_text,
        reason="v2_generated" if validation_ok else "v2_validation_failed",
        evidence_status=retrieval.evidence_status,
        metadata={
            "content_version_id": revision,
            "retrieval_rounds": retrieval.rounds_used,
            "selected_source_ids": retrieval.selected_source_ids,
            "selected_section_ids": retrieval.selected_section_ids,
            "refused_third_round": retrieval.refused_third_round,
            "tool_trace": retrieval.tool_trace,
            "context_compacted": window.context_compacted,
            "context_message_count": len(window.messages),
            "effective_name": facts.effective_name,
            "name_source": facts.name_source,
            "gender": facts.gender,
            "ai_called": True,
            "model": answer.returned_model or answer.requested_model,
            "requested_model_retrieval": retrieval.requested_model,
            "requested_model_answer": answer.requested_model,
            "reasoning_effort_answer": getattr(answer, "effective_reasoning_effort", None) or answer.reasoning_effort,
            "reasoning_effort_retrieval": getattr(retrieval, "effective_reasoning_effort", None) or "none",
            "requested_reasoning_effort_answer": getattr(answer, "requested_reasoning_effort", None),
            "requested_reasoning_effort_retrieval": getattr(retrieval, "requested_reasoning_effort", None),
            "channel_metadata": channel_meta,
            "history_window_minutes": dm_context_window_minutes(),
            "history_messages_loaded": len(shared_history),
            "metering": meter.to_public_dict(),
            "prompt_tokens": prompt_tokens or None,
            "completion_tokens": completion_tokens or None,
            "tokens": total_tokens or None,
            "validated": validation_ok,
            "failed_rules": failed_rules,
            "trace": {**trace, **faq_trace_fields(faq)},
            "faq": faq.metadata or {},
            "faq_direct_reply": False,
            "flags": flags_snapshot(),
            "luna_recommended_tera_effort": retrieval.recommended_tera_effort,
            "authoritative_selector": "retrieval_luna",
            "classic_fallback": False,
            "active_product_id": retrieval.active_product_id,
            "ai_stage_ms": stages_ms,
            **side_meta,
        },
        error=retrieval.error,
    )


# Re-export for tests / public API
from services.customer_reply_v2.comment_runtime import run_customer_reply_v2_comment  # noqa: E402

__all__ = [
    "run_customer_reply_v2_dm",
    "run_customer_reply_v2_comment",
]
