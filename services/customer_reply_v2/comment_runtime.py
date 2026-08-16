"""Comment runtime for Customer Reply AI V2 (no DM 3-hour window)."""

from __future__ import annotations

import time
from typing import Any

from services.customer_reply_v2.answer_luna import run_answer_luna
from services.customer_reply_v2.channel_metadata import build_channel_metadata
from services.customer_reply_v2.customer_facts import load_customer_facts
from services.customer_reply_v2.faq_evidence import merge_faq_evidence
from services.customer_reply_v2.flags import (
    customer_ai_v10_runtime_enabled,
    customer_answer_model_name,
    customer_retrieval_model_name,
    dm_context_window_minutes,
    flags_snapshot,
)
from services.customer_reply_v2.history_format import comment_thread_records, same_history_for_agents
from services.customer_reply_v2.invocation_meter import CustomerTurnMeter
from services.customer_reply_v2.manifest import get_cached_manifest
from services.customer_reply_v2.media_actions import plan_media_for_turn
from services.customer_reply_v2.media_context import build_comment_media_context, media_context_to_dict
from services.customer_reply_v2.models import CustomerReplyOutcome
from services.customer_reply_v2.observability import build_safe_trace
from services.customer_reply_v2.orchestrator_faq import evaluate_faq_turn, faq_direct_outcome_kwargs, faq_trace_fields
from services.customer_reply_v2.orchestrator_validate import safe_failure_reply, validate_candidate
from services.customer_reply_v2.policy import enforce_restricted_and_handoff
from services.customer_reply_v2.retrieval_luna import run_retrieval_luna
from services.customer_reply_v2.safety_gate import evaluate_customer_safety


async def run_customer_reply_v2_comment(
    *,
    tenant_id: str,
    comment_text: str,
    detected_language: str = "ar",
    response_language: str = "ar",
    channel: str = "instagram_comment",
    asset_id: str = "",
    provider_sender_id: str = "",
    provider_display_name: str = "",
    caption: str = "",
    media_type: str = "",
    parent_comment: str = "",
    image_urls: list[str] | None = None,
    media_id: str = "",
    comments_enabled: bool = True,
    comment_context: dict[str, Any] | None = None,
    scripted_retrieval: list[Any] | None = None,
    fixture_answer: dict[str, Any] | None = None,
    injected_media_cache: dict[str, Any] | None = None,
    comment_id: str = "",
    post_id: str = "",
) -> CustomerReplyOutcome:
    """Comment runtime — no DM 3-hour window; shared visual context; one Tera repair."""
    started = time.perf_counter()
    if not comments_enabled:
        return CustomerReplyOutcome(stop=True, reason="comments_toggle_off", reply=None)

    from services.credit_ai_gate import ai_generation_blocked

    if ai_generation_blocked(tenant_id):
        return CustomerReplyOutcome(
            stop=True,
            reply=None,
            reason="insufficient_credits",
            evidence_status="policy_stop",
            metadata={"ai_called": False, "cost_status": "none", "flags": flags_snapshot()},
        )

    from services.cm.language_policy import ensure_customer_languages

    detected_language, response_language = ensure_customer_languages(
        tenant_id=tenant_id,
        message=comment_text,
        detected_language=detected_language,
        response_language=response_language,
        conversation_id=f"comment:{tenant_id}:{channel}",
    )

    revision, _ = get_cached_manifest(tenant_id)
    facts = load_customer_facts(
        tenant_id=tenant_id,
        channel=channel,
        asset_id=asset_id or "default",
        provider_sender_id=provider_sender_id or "unknown",
        provider_display_name=provider_display_name,
    )
    profile = facts.to_safe_dict()
    meter = CustomerTurnMeter(tenant_id=tenant_id)
    v10 = customer_ai_v10_runtime_enabled()

    if comment_context is not None:
        comment_ctx = dict(comment_context)
    else:
        media = build_comment_media_context(
            tenant_id=tenant_id,
            comment_text=comment_text,
            caption=caption,
            media_type=media_type,
            parent_comment=parent_comment,
            image_urls=image_urls,
            media_id=media_id,
            injected_cache=injected_media_cache,
        )
        comment_ctx = media_context_to_dict(media, for_model=True)
        comment_ctx["caption"] = media.caption
        comment_ctx["parent_comment"] = media.parent_comment

    uncertainty = bool(comment_ctx.get("uncertainty_required"))
    channel_meta = build_channel_metadata(
        channel=channel,
        account_id=asset_id,
        post_id=post_id or str(comment_ctx.get("post_id") or ""),
        comment_id=comment_id or str(comment_ctx.get("comment_id") or ""),
        conversation_id=f"comment:{tenant_id}:{channel}",
        can_reply_publicly=True,
        max_media_items=0,
    )
    thread_history = same_history_for_agents(
        comment_thread_records(
            channel=channel,
            comment_text=comment_text,
            parent_comment=str(comment_ctx.get("parent_comment") or parent_comment or ""),
            nearby_replies=list(comment_ctx.get("nearby_replies") or []),
            comment_id=str(channel_meta.get("comment_id") or ""),
            post_id=str(channel_meta.get("post_id") or ""),
        )
    )
    if v10:
        safety = await evaluate_customer_safety(
            tenant_id=tenant_id,
            text=comment_text,
            channel=channel,
            user_id=provider_sender_id or None,
            response_language=response_language,
            is_public=True,
            attachment_types=[str(comment_ctx.get("media_type") or "")] if comment_ctx.get("media_type") else None,
            image_urls=list(comment_ctx.get("image_urls") or image_urls or []),
        )
        if safety.blocked:
            return CustomerReplyOutcome(
                stop=True,
                reply=safety.reply,
                reason="safety_block",
                evidence_status="policy_stop",
                metadata={
                    "ai_called": False,
                    "cost_status": "none",
                    "safety_result": safety.certainty,
                    "safety_policy_version": safety.policy_version,
                    "channel_metadata": channel_meta,
                    "metering": meter.to_public_dict(),
                    "flags": flags_snapshot(),
                },
            )

    policy = enforce_restricted_and_handoff(
        tenant_id=tenant_id,
        message=comment_text,
        response_language=response_language,
        explicit_gender=facts.gender,
        channel=channel,
    )
    if policy:
        return CustomerReplyOutcome(
            stop=True,
            reply=policy["reply"],
            reason=policy["reason"],
            evidence_status="policy_stop",
            metadata={**policy.get("metadata", {}), "comment_context": comment_ctx, "flags": flags_snapshot()},
        )

    faq = await evaluate_faq_turn(
        tenant_id=tenant_id,
        message=comment_text,
        detected_language=detected_language,
        response_language=response_language,
        channel=channel,
        customer_id=provider_sender_id,
        attachment_types=None,
        reply_to=str(comment_ctx.get("parent_comment") or parent_comment or ""),
        has_unresolved_context_refs=bool(comment_ctx.get("caption")) and len(comment_text.split()) <= 3,
    )
    if faq.hit and not uncertainty:
        return CustomerReplyOutcome(
            **faq_direct_outcome_kwargs(
                tenant_id=tenant_id,
                channel=channel,
                revision=revision,
                faq=faq,
                started=started,
                meter=meter,
                extra_metadata={"comment_context": comment_ctx, "channel_metadata": channel_meta},
            )
        )

    try:
        retrieval_model = customer_retrieval_model_name()
        answer_model = customer_answer_model_name()
    except Exception as exc:
        return CustomerReplyOutcome(
            stop=True,
            reply=safe_failure_reply(response_language, kind="model"),
            reason="model_misconfigured",
            error=str(exc),
            evidence_status="insufficient_final",
            metadata={"comment_context": comment_ctx, "flags": flags_snapshot(), "blocker": str(exc)},
        )

    retrieval = await run_retrieval_luna(
        tenant_id=tenant_id,
        message=comment_text,
        customer_profile=profile,
        comment_context=comment_ctx,
        dm_window=thread_history,
        scripted_tool_calls=scripted_retrieval,
        channel=channel,
        channel_metadata=channel_meta,
        faq_candidates=faq.evidence_candidates,
    )
    retrieval = merge_faq_evidence(retrieval, faq.evidence_candidates)

    answer = await run_answer_luna(
        tenant_id=tenant_id,
        message=comment_text,
        retrieval=retrieval,
        customer_profile=profile,
        comment_context=comment_ctx,
        channel=channel,
        response_language=response_language,
        detected_language=detected_language,
        fixture_reply=fixture_answer,
        history_messages=thread_history,
        channel_metadata=channel_meta,
    )

    repair_attempts = 0
    validation_ok = True
    failed_rules: list[str] = []
    reply_text = (answer.reply_text or "")[:900]
    prompt_tokens = int(answer.prompt_tokens or 0)
    completion_tokens = int(answer.completion_tokens or 0)

    if answer.safe_failure_category == "model_unavailable" and not reply_text:
        reply_text = safe_failure_reply(response_language, kind="model")[:900]
        failed_rules = ["answer_model_unavailable"]

    if retrieval.evidence_status == "insufficient_final" and not reply_text:
        reply_text = safe_failure_reply(response_language, kind="insufficient")[:900]

    if reply_text and retrieval.evidence and "answer_model_unavailable" not in failed_rules:
        validation_ok, failed_rules = validate_candidate(
            tenant_id=tenant_id,
            candidate=reply_text,
            retrieval=retrieval,
            detected_language=detected_language,
            response_language=response_language,
        )
        if not validation_ok:
            repair_attempts = 1
            repaired = await run_answer_luna(
                tenant_id=tenant_id,
                message=comment_text,
                retrieval=retrieval,
                customer_profile=profile,
                comment_context=comment_ctx,
                channel=channel,
                response_language=response_language,
                detected_language=detected_language,
                fixture_reply=(
                    {**fixture_answer, "reply_text": fixture_answer.get("repair_reply_text", reply_text)}
                    if fixture_answer
                    else None
                ),
                repair_failures=failed_rules,
                history_messages=thread_history,
                channel_metadata=channel_meta,
            )
            reply_text = (repaired.reply_text or "")[:900]
            prompt_tokens += int(repaired.prompt_tokens or 0)
            completion_tokens += int(repaired.completion_tokens or 0)
            answer = repaired
            validation_ok, failed_rules = validate_candidate(
                tenant_id=tenant_id,
                candidate=reply_text,
                retrieval=retrieval,
                detected_language=detected_language,
                response_language=response_language,
            )
            if not validation_ok:
                reply_text = safe_failure_reply(response_language, kind="validation", public=True)[:900]
                validation_ok = True
                failed_rules = failed_rules + ["safe_failure_fallback"]

    # Observability strip: do not dump multimodal data URLs into traces.
    trace_ctx = {k: v for k, v in comment_ctx.items() if k != "image_inputs"}
    total_tokens = prompt_tokens + completion_tokens
    media_meta = plan_media_for_turn(
        tenant_id=tenant_id,
        answer=answer,
        channel_metadata=channel_meta,
        meter=meter,
        idempotency_key=meter.customer_turn_id,
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
        requested_models={"retrieval": retrieval_model, "answer": answer_model},
        returned_models={"retrieval": retrieval.returned_model, "answer": answer.returned_model},
        context_message_count=len(thread_history),
        context_compacted=False,
        delivery_result="ready_to_send",
        latency_ms=(time.perf_counter() - started) * 1000,
        stage="repair" if repair_attempts else "answer",
        reasoning_effort={
            "retrieval_requested": retrieval.requested_reasoning_effort,
            "retrieval_effective": retrieval.effective_reasoning_effort,
            "answer_requested": answer.requested_reasoning_effort,
            "answer_effective": answer.effective_reasoning_effort,
        },
        prompt_tokens=prompt_tokens or None,
        completion_tokens=completion_tokens or None,
        total_tokens=total_tokens or None,
    )

    return CustomerReplyOutcome(
        stop=True,
        reply=reply_text or None,
        reason="v2_comment_generated",
        evidence_status=retrieval.evidence_status,
        metadata={
            "content_version_id": revision,
            "comment_context": trace_ctx,
            "selected_source_ids": retrieval.selected_source_ids,
            "retrieval_rounds": retrieval.rounds_used,
            "refused_third_round": retrieval.refused_third_round,
            "flags": flags_snapshot(),
            "dm_history_mixed": False,
            "model": answer.returned_model or answer_model,
            "requested_model_retrieval": retrieval.requested_model,
            "requested_model_answer": answer.requested_model,
            "reasoning_effort_answer": answer.effective_reasoning_effort or answer.reasoning_effort,
            "channel_metadata": channel_meta,
            "history_window_minutes": dm_context_window_minutes(),
            "history_messages_loaded": len(thread_history),
            "metering": meter.to_public_dict(),
            "media_status": comment_ctx.get("media_status"),
            "validated": validation_ok,
            "failed_rules": failed_rules,
            "trace": {**trace, **faq_trace_fields(faq)},
            "faq_direct_reply": False,
            "classic_fallback": False,
            "prompt_tokens": prompt_tokens or None,
            "completion_tokens": completion_tokens or None,
            "tokens": total_tokens or None,
            **media_meta,
        },
    )
