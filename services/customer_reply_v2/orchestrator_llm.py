"""Luna retrieval then Tera answer with stage timings. Product models unchanged."""

from __future__ import annotations

import time
from typing import Any

from services.customer_reply_v2.answer_luna import run_answer_luna
from services.customer_reply_v2.faq_evidence import merge_faq_evidence
from services.customer_reply_v2.flags import customer_answer_model_name, customer_retrieval_model_name
from services.customer_reply_v2.invocation_meter import CustomerTurnMeter, InvocationRecord
from services.customer_reply_v2.models import AnswerLunaResult, RetrievalResult
from services.customer_reply_v2.orchestrator_answer import finalize_answer_with_repair
from services.customer_reply_v2.retrieval_business_fallback import ensure_dm_business_evidence
from services.customer_reply_v2.retrieval_luna import run_retrieval_luna
from services.scale.ai_stage_timing import record_gap_ms, time_stage


async def run_dm_luna_then_tera(
    *,
    tenant_id: str,
    message: str,
    profile: dict[str, Any],
    luna_history: list[dict[str, Any]],
    tera_history: list[dict[str, Any]],
    scripted_retrieval: Any,
    conversation_id: str,
    channel: str,
    reply_to_message_id: str,
    channel_meta: dict[str, Any],
    faq_candidates: list[Any],
    provider_sender_id: str,
    user_id: str,
    asset_id: str,
    response_language: str,
    detected_language: str,
    fixture_answer: dict[str, Any] | None,
    meter: CustomerTurnMeter,
) -> tuple[RetrievalResult | None, AnswerLunaResult | None, dict[str, Any]]:
    """Run retrieval (Luna) then answer (Tera). Returns (retrieval, answer, extra).

    extra has stages_ms and, when retrieval is blocked, blocker fields.
    """
    retrieval_model = customer_retrieval_model_name()
    answer_model = customer_answer_model_name()
    stages: dict[str, float] = {}
    async with time_stage("luna") as luna_slot:
        retrieval = await run_retrieval_luna(
            tenant_id=tenant_id,
            message=message,
            customer_profile=profile,
            dm_window=luna_history,
            scripted_tool_calls=scripted_retrieval,
            conversation_id=conversation_id or None,
            channel=channel,
            reply_to_message_id=reply_to_message_id or None,
            channel_metadata=channel_meta,
            faq_candidates=faq_candidates,
            customer_id=provider_sender_id or user_id,
        )
    stages["luna_ms"] = float(luna_slot.get("ms") or 0.0)
    gap_started = time.perf_counter()
    retrieval = merge_faq_evidence(retrieval, faq_candidates)
    retrieval = ensure_dm_business_evidence(retrieval, tenant_id=tenant_id, channel=channel)
    gap_ms = max(0.0, (time.perf_counter() - gap_started) * 1000.0)
    stages["luna_tera_gap_ms"] = gap_ms
    record_gap_ms("luna", "tera", gap_ms)
    meter.record(
        InvocationRecord(
            operation="luna_retrieval",
            model=retrieval.requested_model or retrieval_model,
            requested_reasoning_effort=retrieval.requested_reasoning_effort,
            effective_reasoning_effort=retrieval.effective_reasoning_effort,
            input_tokens=retrieval.prompt_tokens,
            output_tokens=retrieval.completion_tokens,
            tool_rounds=retrieval.rounds_used,
            success=not bool(retrieval.error),
            failure_stage=retrieval.error,
        )
    )
    if retrieval.error and retrieval.error.startswith("retrieval_model_blocker:"):
        return retrieval, None, {"blocker": retrieval.error, "stages_ms": stages}

    async with time_stage("tera") as tera_slot:
        answer = await run_answer_luna(
            tenant_id=tenant_id,
            message=message,
            retrieval=retrieval,
            customer_profile=profile,
            history_messages=tera_history,
            channel=channel,
            conversation_id=conversation_id or None,
            asset_id=asset_id or None,
            provider_sender_id=provider_sender_id or user_id or None,
            response_language=response_language,
            detected_language=detected_language,
            fixture_reply=fixture_answer,
            channel_metadata=channel_meta,
        )
        pack = await finalize_answer_with_repair(
            tenant_id=tenant_id,
            message=message,
            retrieval=retrieval,
            customer_profile=profile,
            tera_history=tera_history,
            channel=channel,
            conversation_id=conversation_id or None,
            asset_id=asset_id or None,
            provider_sender_id=provider_sender_id or user_id or None,
            response_language=response_language,
            detected_language=detected_language,
            fixture_answer=fixture_answer,
            channel_meta=channel_meta,
            answer=answer,
        )
    stages["tera_ms"] = float(tera_slot.get("ms") or 0.0)
    answer, reply_text, prompt_tokens, completion_tokens, repair_attempts, validation_ok, failed_rules = pack
    meter.record(
        InvocationRecord(
            operation="tera_repair" if repair_attempts else "tera_answer",
            model=answer.returned_model or answer_model,
            requested_reasoning_effort=answer.requested_reasoning_effort,
            effective_reasoning_effort=answer.effective_reasoning_effort,
            input_tokens=answer.prompt_tokens,
            output_tokens=answer.completion_tokens,
            repair=bool(repair_attempts),
            success=bool(reply_text),
        )
    )
    return (
        retrieval,
        answer,
        {
            "stages_ms": stages,
            "reply_text": reply_text,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "repair_attempts": repair_attempts,
            "validation_ok": validation_ok,
            "failed_rules": failed_rules,
        },
    )
