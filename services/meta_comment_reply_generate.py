"""Generate one public Meta comment reply via Customer Reply AI V2."""

from __future__ import annotations

import logging
from typing import Any

_runtime_logger = logging.getLogger("uvicorn.error")


class MetaCommentReplyGenerationError(RuntimeError):
    """Transient AI generation failure that should remain eligible for retry."""


async def generate_comment_reply_text(
    *,
    tenant_id: str,
    comment_text: str,
    instructions: str,
    channel: str,
    policy_text: str = "",
    comment_context: dict[str, Any] | None = None,
    asset_id: str = "",
    provider_sender_id: str = "",
    provider_display_name: str = "",
) -> str | None:
    """Generate a public comment reply via Customer Reply AI V2 only (CM tenants).

    Never falls back to Classic ``generate_answer_with_usage``. Non-CM tenants keep
    the pre-existing local FAQ matcher (not Classic CM generative).
    """
    from services.cm.constants import tenant_uses_cm_runtime
    from services.cm.language_policy import detect_and_resolve_customer_languages

    _lang = detect_and_resolve_customer_languages(
        tenant_id=tenant_id,
        message=comment_text,
        conversation_id=f"comment:{tenant_id}:{channel}",
    )
    detected_language = _lang["detected_language"]
    response_language = _lang["response_language"]

    if tenant_uses_cm_runtime(tenant_id):
        from services.customer_reply_v2.comment_runtime import run_customer_reply_v2_comment

        social_channel = "facebook_comment" if channel == "facebook" else "instagram_comment"
        enriched = dict(comment_context or {})
        if instructions and "asset_instructions" not in enriched:
            enriched["asset_instructions"] = instructions.strip()[:800]
        if policy_text and "comments_policy" not in enriched:
            enriched["comments_policy"] = {"policy_text": policy_text.strip()[:1200]}
        try:
            v2_outcome = await run_customer_reply_v2_comment(
                tenant_id=tenant_id,
                comment_text=comment_text,
                detected_language=detected_language,
                response_language=response_language,
                channel=social_channel,
                asset_id=asset_id,
                provider_sender_id=provider_sender_id,
                provider_display_name=provider_display_name,
                comments_enabled=True,
                comment_context=enriched or None,
            )
        except Exception as v2_exc:
            _runtime_logger.warning(
                "customer_reply_v2 comment path failed closed: %s",
                type(v2_exc).__name__,
            )
            raise MetaCommentReplyGenerationError("customer reply generation failed") from v2_exc
        if v2_outcome.reply:
            return str(v2_outcome.reply).strip()[:900]
        return None

    from services.local_qa_service import local_qa_service

    tiered_match = await local_qa_service.find_match_with_tier(comment_text, "ar")
    if tiered_match and tiered_match.get("answer"):
        return str(tiered_match["answer"]).strip()[:900]
    return None
