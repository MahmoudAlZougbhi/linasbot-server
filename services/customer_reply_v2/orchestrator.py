"""Customer Reply AI V2 orchestrator — DM and comment runtimes (production sole engine)."""

from __future__ import annotations

import time
from typing import Any

from services.cm.answer_packet import build_answer_packet
from services.cm.response_validator import validate_response
from services.cm.schemas import AnswerChunk, AnswerFact
from services.cm.version_store import PublishedVersionError, load_published_content
from services.customer_reply_v2.answer_luna import run_answer_luna
from services.customer_reply_v2.conversation_window import filter_rolling_window, load_dm_conversation_window
from services.customer_reply_v2.customer_facts import apply_message_fact_updates, load_customer_facts
from services.customer_reply_v2.faq_fast_path import try_faq_fast_path
from services.customer_reply_v2.flags import (
    customer_answer_model_name,
    customer_retrieval_model_name,
    customer_semantic_retrieval_enabled,
    flags_snapshot,
)
from services.customer_reply_v2.manifest import get_cached_manifest, load_fixed_answer_context
from services.customer_reply_v2.models import CustomerReplyOutcome, RetrievalResult
from services.customer_reply_v2.observability import build_safe_trace
from services.customer_reply_v2.policy import enforce_restricted_and_handoff
from services.customer_reply_v2.retrieval_luna import run_retrieval_luna


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
        messages = {
            "ar": "خليني تأكدلك المعلومة صح — راسلنا على واتساب لنساعدك بدقة.",
            "en": "Let me make sure this is accurate — please reach us on WhatsApp for a precise answer.",
            "fr": "Laissez-moi vérifier — contactez-nous sur WhatsApp pour une réponse précise.",
            "franco": "Khallini akked el maaloome — rasilna 3a WhatsApp la jawab sahih.",
        }
    return messages.get(response_language, messages["en"])


async def run_customer_reply_v2_dm(
    *,
    tenant_id: str,
    message: str,
    detected_language: str,
    response_language: str,
    channel: str = "instagram_dm",
    asset_id: str = "",
    provider_sender_id: str = "",
    provider_display_name: str = "",
    user_id: str = "",
    conversation_id: str = "",
    injected_history: list[dict[str, Any]] | None = None,
    scripted_retrieval: list[Any] | None = None,
    fixture_answer: dict[str, Any] | None = None,
    now_ts: float | None = None,
) -> CustomerReplyOutcome:
    """Canonical DM flow for Customer Reply AI V2 (sole production engine)."""
    started = time.perf_counter()

    try:
        revision, _manifest = get_cached_manifest(tenant_id)
    except PublishedVersionError:
        return CustomerReplyOutcome(
            stop=True,
            reply=_safe_failure_reply(response_language, kind="insufficient"),
            reason="no_published_version",
            evidence_status="insufficient_final",
            metadata={"classic_fallback": False, "flags": flags_snapshot()},
            error="no_published_version",
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

    policy = enforce_restricted_and_handoff(
        tenant_id=tenant_id,
        message=message,
        response_language=response_language,
        explicit_gender=facts.gender,
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
        return CustomerReplyOutcome(
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
    # Current inbound is separate/explicit — exclude duplicate trailing twin if present.
    if history_msgs and history_msgs[-1].get("role") == "user" and history_msgs[-1].get("content") == message:
        history_for_model = history_msgs[:-1]
    else:
        history_for_model = history_msgs

    faq = await try_faq_fast_path(
        tenant_id=tenant_id,
        message=message,
        detected_language=detected_language,
        has_unresolved_context_refs=False,
    )
    if faq.hit:
        trace = build_safe_trace(
            tenant_id=tenant_id,
            channel=channel,
            published_revision=revision,
            faq_category=faq.reason,
            retrieval_rounds=0,
            selected_source_ids=[],
            evidence_status="faq_hit",
            validation_ok=True,
            repair_attempts=0,
            requested_models={},
            returned_models={},
            context_message_count=len(window.messages),
            context_compacted=window.context_compacted,
            delivery_result="faq_reply",
            latency_ms=(time.perf_counter() - started) * 1000,
            stage="faq",
        )
        return CustomerReplyOutcome(
            stop=True,
            reply=faq.answer,
            reason=faq.reason,
            evidence_status="faq_hit",
            metadata={"faq": faq.metadata or {}, "trace": trace, "flags": flags_snapshot()},
        )

    if not customer_semantic_retrieval_enabled():
        return CustomerReplyOutcome(
            stop=True,
            reply=_safe_failure_reply(response_language, kind="model"),
            reason="semantic_retrieval_disabled",
            error="CUSTOMER_SEMANTIC_RETRIEVAL_ENABLED=false",
            evidence_status="insufficient_final",
            metadata={"flags": flags_snapshot(), "blocker": "semantic_retrieval_disabled"},
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
            metadata={"flags": flags_snapshot(), "blocker": str(exc)},
        )

    retrieval = await run_retrieval_luna(
        tenant_id=tenant_id,
        message=message,
        customer_profile=profile,
        dm_window=[{"role": m["role"], "content": m["content"]} for m in history_for_model],
        scripted_tool_calls=scripted_retrieval,
    )
    if retrieval.error and retrieval.error.startswith("retrieval_model_blocker:"):
        return CustomerReplyOutcome(
            stop=True,
            reply=_safe_failure_reply(response_language, kind="model"),
            reason="retrieval_model_blocker",
            error=retrieval.error,
            evidence_status="insufficient_final",
            metadata={"flags": flags_snapshot(), "blocker": retrieval.error},
        )

    answer = await run_answer_luna(
        tenant_id=tenant_id,
        message=message,
        retrieval=retrieval,
        customer_profile=profile,
        history_messages=[{"role": m["role"], "content": m["content"]} for m in history_for_model],
        channel=channel,
        response_language=response_language,
        detected_language=detected_language,
        fixture_reply=fixture_answer,
    )

    repair_attempts = 0
    validation_ok = True
    failed_rules: list[str] = []
    reply_text = answer.reply_text
    prompt_tokens = int(answer.prompt_tokens or 0)
    completion_tokens = int(answer.completion_tokens or 0)

    if answer.safe_failure_category == "model_unavailable" and not reply_text:
        reply_text = _safe_failure_reply(response_language, kind="model")
        validation_ok = True
        failed_rules = ["answer_model_unavailable"]

    if retrieval.evidence_status == "insufficient_final" and not reply_text:
        reply_text = _safe_failure_reply(response_language, kind="insufficient")

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
                message=message,
                retrieval=retrieval,
                customer_profile=profile,
                history_messages=[{"role": m["role"], "content": m["content"]} for m in history_for_model],
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
            reply_text = repaired.reply_text
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
                reply_text = _safe_failure_reply(response_language, kind="validation")
                # Safe failure — never send the invalid candidate; never Classic.
                validation_ok = True
                failed_rules = failed_rules + ["safe_failure_fallback"]

    # Prove fixed answer context was loaded for generated path
    fixed = load_fixed_answer_context(tenant_id)
    assert "ai_basics" in fixed and "style" in fixed

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
        requested_models={
            "retrieval": retrieval.requested_model or retrieval_model,
            "answer": answer.requested_model or answer_model,
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
        reasoning_effort={"retrieval": "none", "answer": "medium"},
        prompt_tokens=prompt_tokens or None,
        completion_tokens=completion_tokens or None,
        total_tokens=total_tokens or None,
    )

    return CustomerReplyOutcome(
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
            "model": answer.returned_model or answer_model,
            "requested_model_retrieval": retrieval.requested_model,
            "requested_model_answer": answer.requested_model,
            "reasoning_effort_answer": "medium",
            "reasoning_effort_retrieval": "none",
            "prompt_tokens": prompt_tokens or None,
            "completion_tokens": completion_tokens or None,
            "tokens": total_tokens or None,
            "validated": validation_ok,
            "failed_rules": failed_rules,
            "trace": trace,
            "flags": flags_snapshot(),
            "authoritative_selector": "retrieval_luna",
            "classic_fallback": False,
        },
        error=retrieval.error,
    )


# Re-export for tests / public API
from services.customer_reply_v2.comment_runtime import run_customer_reply_v2_comment  # noqa: E402

__all__ = [
    "run_customer_reply_v2_dm",
    "run_customer_reply_v2_comment",
    "filter_rolling_window",
]
