"""Comment runtime for Customer Reply AI V2 (no DM 3-hour window)."""

from __future__ import annotations

from typing import Any

from services.customer_reply_v2.answer_luna import run_answer_luna
from services.customer_reply_v2.customer_facts import load_customer_facts
from services.customer_reply_v2.faq_fast_path import try_faq_fast_path
from services.customer_reply_v2.flags import (
    customer_reply_ai_v2_enabled,
    customer_reply_ai_v2_live_send,
    flags_snapshot,
)
from services.customer_reply_v2.manifest import get_cached_manifest
from services.customer_reply_v2.media_context import build_comment_media_context, media_context_to_dict
from services.customer_reply_v2.models import CustomerReplyOutcome
from services.customer_reply_v2.policy import enforce_restricted_and_handoff
from services.customer_reply_v2.retrieval_luna import run_retrieval_luna


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
    scripted_retrieval: list[Any] | None = None,
    fixture_answer: dict[str, Any] | None = None,
    injected_media_cache: dict[str, Any] | None = None,
) -> CustomerReplyOutcome:
    """Comment runtime — no DM 3-hour window; separate media context."""
    shadow = not customer_reply_ai_v2_live_send()
    if not customer_reply_ai_v2_enabled():
        return CustomerReplyOutcome(stop=True, reason="v2_disabled", error="CUSTOMER_REPLY_AI_V2=false")
    if not comments_enabled:
        return CustomerReplyOutcome(stop=True, reason="comments_toggle_off", reply=None, shadow_only=shadow)

    revision, _ = get_cached_manifest(tenant_id)
    facts = load_customer_facts(
        tenant_id=tenant_id,
        channel=channel,
        asset_id=asset_id or "default",
        provider_sender_id=provider_sender_id or "unknown",
        provider_display_name=provider_display_name,
    )
    profile = facts.to_safe_dict()

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
    comment_ctx = media_context_to_dict(media)
    comment_ctx["caption"] = media.caption
    comment_ctx["parent_comment"] = media.parent_comment

    policy = enforce_restricted_and_handoff(
        tenant_id=tenant_id,
        message=comment_text,
        response_language=response_language,
        explicit_gender=facts.gender,
    )
    if policy:
        return CustomerReplyOutcome(
            stop=True,
            reply=policy["reply"],
            reason=policy["reason"],
            evidence_status="policy_stop",
            metadata={**policy.get("metadata", {}), "comment_context": comment_ctx, "flags": flags_snapshot()},
            shadow_only=shadow,
        )

    faq = await try_faq_fast_path(
        tenant_id=tenant_id,
        message=comment_text,
        detected_language=detected_language,
        has_unresolved_context_refs=bool(caption) and len(comment_text.split()) <= 3,
    )
    if faq.hit and not media.uncertainty_required:
        return CustomerReplyOutcome(
            stop=True,
            reply=faq.answer,
            reason=faq.reason,
            evidence_status="faq_hit",
            metadata={"faq": faq.metadata or {}, "comment_context": comment_ctx, "flags": flags_snapshot()},
            shadow_only=shadow,
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
        fixture_reply=fixture_answer,
    )
    reply = (answer.reply_text or "")[:900]
    return CustomerReplyOutcome(
        stop=True,
        reply=reply or None,
        reason="v2_comment_generated",
        evidence_status=retrieval.evidence_status,
        metadata={
            "content_version_id": revision,
            "comment_context": comment_ctx,
            "selected_source_ids": retrieval.selected_source_ids,
            "retrieval_rounds": retrieval.rounds_used,
            "refused_third_round": retrieval.refused_third_round,
            "flags": flags_snapshot(),
            "dm_history_mixed": False,
        },
        shadow_only=shadow,
    )
