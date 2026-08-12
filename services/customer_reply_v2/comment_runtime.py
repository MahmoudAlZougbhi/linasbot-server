"""Comment runtime for Customer Reply AI V2 (no DM 3-hour window)."""

from __future__ import annotations

import time
from typing import Any

from services.cm.answer_packet import build_answer_packet
from services.cm.response_validator import validate_response
from services.cm.schemas import AnswerChunk, AnswerFact
from services.cm.version_store import load_published_content
from services.customer_reply_v2.answer_luna import run_answer_luna
from services.customer_reply_v2.customer_facts import load_customer_facts
from services.customer_reply_v2.faq_fast_path import try_faq_fast_path
from services.customer_reply_v2.flags import (
    customer_answer_model_name,
    customer_retrieval_model_name,
    flags_snapshot,
)
from services.customer_reply_v2.manifest import get_cached_manifest
from services.customer_reply_v2.media_context import build_comment_media_context, media_context_to_dict
from services.customer_reply_v2.models import CustomerReplyOutcome, RetrievalResult
from services.customer_reply_v2.observability import build_safe_trace
from services.customer_reply_v2.policy import enforce_restricted_and_handoff
from services.customer_reply_v2.retrieval_luna import run_retrieval_luna


def _safe_failure_reply(response_language: str, *, kind: str = "validation") -> str:
    if kind == "model":
        messages = {
            "ar": "الخدمة الذكية غير متاحة حالياً. تواصل معنا مباشرة وسنساعدك.",
            "en": "Our AI reply service is temporarily unavailable. Please contact us directly.",
            "fr": "Le service de réponse IA est temporairement indisponible. Contactez-nous directement.",
            "franco": "El AI reply mesh available halla2. Contactuna mubasharan.",
        }
    elif kind == "insufficient":
        messages = {
            "ar": "ما قدرت أكد المعلومة من المحتوى المنشور حالياً. بقدر وجهك لفريقنا إذا حابب.",
            "en": "I couldn't confirm that from our published content. I can connect you with our team if you'd like.",
            "fr": "Je n'ai pas pu confirmer cela dans notre contenu publié. Je peux vous mettre en relation avec notre équipe.",
            "franco": "Ma ederet akked el maaloome men el content. Fini a3teek el team iza baddak.",
        }
    else:
        # Public-comment safe: invite DM only — never phone / wa.me destinations.
        messages = {
            "ar": "خليني تأكدلك المعلومة صح — راسلنا بالخاص (DM) لنساعدك بدقة.",
            "en": "Let me make sure this is accurate — please message us in DM for a precise answer.",
            "fr": "Laissez-moi vérifier — écrivez-nous en message privé (DM) pour une réponse précise.",
            "franco": "Khallini akked el maaloome — rasilna bil DM la jawab sahih.",
        }
    return messages.get(response_language, messages["en"])


def _facts_to_answer_facts(retrieval: RetrievalResult) -> tuple[list[AnswerFact], list[AnswerChunk]]:
    facts: list[AnswerFact] = []
    chunks: list[AnswerChunk] = []
    for ev in retrieval.evidence:
        if ev.section_id in {"prices", "services", "branches", "handoff", "off_days"}:
            facts.append(AnswerFact(kind=ev.section_id, value=ev.content[:500], source_id=ev.source_id))
        else:
            chunks.append(AnswerChunk(source_id=ev.source_id, text=ev.content, score=None))
    return facts, chunks


def _validate_candidate(
    *,
    tenant_id: str,
    candidate: str,
    retrieval: RetrievalResult,
    detected_language: str,
    response_language: str,
) -> tuple[bool, list[str]]:
    pointer, sections = load_published_content(tenant_id)
    facts, chunks = _facts_to_answer_facts(retrieval)
    packet = build_answer_packet(
        tenant_id=tenant_id,
        content_version_id=pointer.content_version_id,
        index_version_id=pointer.index_version_id,
        detected_language=detected_language,
        response_language=response_language,
        sections=sections,
        facts=facts,
        chunks=chunks,
    )
    result = validate_response(candidate, packet)
    return result.ok, list(result.failed_rules or [])


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
) -> CustomerReplyOutcome:
    """Comment runtime — no DM 3-hour window; shared visual context; one Tera repair."""
    started = time.perf_counter()
    if not comments_enabled:
        return CustomerReplyOutcome(stop=True, reason="comments_toggle_off", reply=None)

    revision, _ = get_cached_manifest(tenant_id)
    facts = load_customer_facts(
        tenant_id=tenant_id,
        channel=channel,
        asset_id=asset_id or "default",
        provider_sender_id=provider_sender_id or "unknown",
        provider_display_name=provider_display_name,
    )
    profile = facts.to_safe_dict()

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

    faq = await try_faq_fast_path(
        tenant_id=tenant_id,
        message=comment_text,
        detected_language=detected_language,
        has_unresolved_context_refs=bool(comment_ctx.get("caption")) and len(comment_text.split()) <= 3,
    )
    if faq.hit and not uncertainty:
        return CustomerReplyOutcome(
            stop=True,
            reply=faq.answer,
            reason=faq.reason,
            evidence_status="faq_hit",
            metadata={"faq": faq.metadata or {}, "comment_context": comment_ctx, "flags": flags_snapshot()},
        )

    try:
        retrieval_model = customer_retrieval_model_name()
        answer_model = customer_answer_model_name()
    except Exception as exc:
        return CustomerReplyOutcome(
            stop=True,
            reply=_safe_failure_reply(response_language, kind="model"),
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
        scripted_tool_calls=scripted_retrieval,
    )

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
    )

    repair_attempts = 0
    validation_ok = True
    failed_rules: list[str] = []
    reply_text = (answer.reply_text or "")[:900]
    prompt_tokens = int(answer.prompt_tokens or 0)
    completion_tokens = int(answer.completion_tokens or 0)

    if answer.safe_failure_category == "model_unavailable" and not reply_text:
        reply_text = _safe_failure_reply(response_language, kind="model")[:900]
        failed_rules = ["answer_model_unavailable"]

    if retrieval.evidence_status == "insufficient_final" and not reply_text:
        reply_text = _safe_failure_reply(response_language, kind="insufficient")[:900]

    if reply_text and retrieval.evidence and "answer_model_unavailable" not in failed_rules:
        validation_ok, failed_rules = _validate_candidate(
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
            )
            reply_text = (repaired.reply_text or "")[:900]
            prompt_tokens += int(repaired.prompt_tokens or 0)
            completion_tokens += int(repaired.completion_tokens or 0)
            answer = repaired
            validation_ok, failed_rules = _validate_candidate(
                tenant_id=tenant_id,
                candidate=reply_text,
                retrieval=retrieval,
                detected_language=detected_language,
                response_language=response_language,
            )
            if not validation_ok:
                reply_text = _safe_failure_reply(response_language, kind="validation")[:900]
                validation_ok = True
                failed_rules = failed_rules + ["safe_failure_fallback"]

    # Observability strip: do not dump multimodal data URLs into traces.
    trace_ctx = {k: v for k, v in comment_ctx.items() if k != "image_inputs"}
    total_tokens = prompt_tokens + completion_tokens
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
        context_message_count=0,
        context_compacted=False,
        delivery_result="ready_to_send",
        latency_ms=(time.perf_counter() - started) * 1000,
        stage="repair" if repair_attempts else "answer",
        reasoning_effort={"retrieval": "none", "answer": "medium"},
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
            "reasoning_effort_answer": "medium",
            "media_status": comment_ctx.get("media_status"),
            "validated": validation_ok,
            "failed_rules": failed_rules,
            "trace": trace,
            "classic_fallback": False,
            "prompt_tokens": prompt_tokens or None,
            "completion_tokens": completion_tokens or None,
            "tokens": total_tokens or None,
        },
    )
