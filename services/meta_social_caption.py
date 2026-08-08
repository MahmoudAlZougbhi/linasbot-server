"""Generate social post captions from the workspace knowledge base."""

from __future__ import annotations

from services.cm.constants import cm_runtime_mode

_CAPTION_SYSTEM_RULES = (
    "You are drafting a short social media post caption for a business. "
    "Write 1-3 concise sentences suitable for Facebook or Instagram. "
    "Use only facts from the approved business content. "
    "Do not invent prices, discounts, opening hours, medical claims, or services. "
    "Do not include hashtags unless they appear in approved content. "
    "Do not promise results or make medical guarantees. "
    "If unsure, keep the caption general and invite followers to send a private message."
)


async def generate_social_caption(
    *,
    tenant_id: str,
    topic: str = "",
    platforms: list[str] | None = None,
) -> str | None:
    platform_hint = ", ".join(platforms or ["facebook", "instagram"])
    prompt = (
        f"{_CAPTION_SYSTEM_RULES}\n"
        f"Platforms: {platform_hint}.\n"
        f"Topic or brief: {(topic or 'general business update').strip()}\n"
    )

    if cm_runtime_mode() == "published":
        from services.cm.answer_generation import (
            UsageAccumulator,
            generate_answer_with_usage,
            make_regenerate_fn_with_usage,
        )
        from services.cm.runtime_pipeline import finalize_response, prepare_response

        seed = (topic or "social post caption").strip()
        outcome = await prepare_response(
            tenant_id=tenant_id,
            message=seed,
            detected_language="ar",
            response_language="ar",
        )
        if outcome.stop:
            reply = (outcome.reply or "").strip()
            return reply[:2200] if reply else None
        packet = outcome.packet
        if packet is None:
            return None
        usage_acc = UsageAccumulator()
        try:
            gen_result = await generate_answer_with_usage(f"{prompt}\n{seed}", packet)
            candidate_text = gen_result.text
            if gen_result.prompt_tokens is not None or gen_result.completion_tokens is not None:
                usage_acc.prompt_tokens += int(gen_result.prompt_tokens or 0)
                usage_acc.completion_tokens += int(gen_result.completion_tokens or 0)
                usage_acc.calls += max(int(gen_result.call_count or 1), 1)
                usage_acc.models.append(gen_result.model)
        except Exception:
            return None
        restricted_ids = set(outcome.metadata.get("restricted_topic_active_ids") or [])
        result = await finalize_response(
            candidate_text=candidate_text,
            packet=packet,
            restricted_topic_active_ids=restricted_ids,
            regenerate_fn=make_regenerate_fn_with_usage(seed, packet, usage_acc),
        )
        text = str(result.text or "").strip()
        return text[:2200] if text and result.ok else None

    from services.local_qa_service import local_qa_service

    tiered_match = await local_qa_service.find_match_with_tier(topic or "services", "ar")
    if tiered_match and tiered_match.get("answer"):
        return str(tiered_match["answer"]).strip()[:2200]
    return None
