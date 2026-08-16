"""Answer + one-repair loop for Customer Reply V2."""

from __future__ import annotations

from typing import Any

from services.customer_reply_v2.answer_luna import run_answer_luna
from services.customer_reply_v2.models import AnswerLunaResult, RetrievalResult
from services.customer_reply_v2.orchestrator_validate import safe_failure_reply, validate_candidate


async def finalize_answer_with_repair(
    *,
    tenant_id: str,
    message: str,
    retrieval: RetrievalResult,
    customer_profile: dict[str, Any],
    tera_history: list[dict[str, Any]],
    channel: str,
    conversation_id: str | None,
    asset_id: str | None,
    provider_sender_id: str | None,
    response_language: str,
    detected_language: str,
    fixture_answer: dict[str, Any] | None,
    channel_meta: dict[str, Any],
    answer: AnswerLunaResult,
) -> tuple[AnswerLunaResult, str, int, int, int, bool, list[str]]:
    repair_attempts = 0
    validation_ok = True
    failed_rules: list[str] = []
    reply_text = answer.reply_text
    prompt_tokens = int(answer.prompt_tokens or 0)
    completion_tokens = int(answer.completion_tokens or 0)

    if answer.safe_failure_category == "model_unavailable" and not reply_text:
        reply_text = safe_failure_reply(response_language, kind="model")
        validation_ok = True
        failed_rules = ["answer_model_unavailable"]

    if retrieval.evidence_status == "insufficient_final" and not reply_text:
        reply_text = safe_failure_reply(response_language, kind="insufficient")

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
                message=message,
                retrieval=retrieval,
                customer_profile=customer_profile,
                history_messages=tera_history,
                channel=channel,
                conversation_id=conversation_id,
                asset_id=asset_id,
                provider_sender_id=provider_sender_id,
                response_language=response_language,
                detected_language=detected_language,
                fixture_reply=(
                    {**fixture_answer, "reply_text": fixture_answer.get("repair_reply_text", reply_text)}
                    if fixture_answer
                    else None
                ),
                repair_failures=failed_rules,
                channel_metadata=channel_meta,
            )
            reply_text = repaired.reply_text
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
                reply_text = safe_failure_reply(response_language, kind="validation")
                validation_ok = True
                failed_rules = failed_rules + ["safe_failure_fallback"]
    return answer, reply_text, prompt_tokens, completion_tokens, repair_attempts, validation_ok, failed_rules
