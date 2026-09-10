"""Customer DM reply facade. Luna/Terra are gone; inbound still saves via callers."""

from __future__ import annotations

from typing import Any

from services.customer_reply_v2.models import ENGINE_REMOVED, CustomerReplyOutcome


def _removed_outcome() -> CustomerReplyOutcome:
    return CustomerReplyOutcome(
        stop=True,
        reply=None,
        reason=ENGINE_REMOVED,
        evidence_status="policy_stop",
        metadata={"ai_called": False, "cost_status": "none", "customer_engine": "removed"},
    )


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
    """Stable entry point for all DM channels. New engine will replace this body."""
    _ = (
        tenant_id,
        message,
        detected_language,
        response_language,
        channel,
        asset_id,
        provider_sender_id,
        provider_display_name,
        user_id,
        conversation_id,
        reply_to_message_id,
        message_id,
        attachment_types,
        inbound_media,
        injected_history,
        scripted_retrieval,
        fixture_answer,
        now_ts,
        apply_customer_usage_limits,
    )
    return _removed_outcome()


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
    from services.customer_reply_v2.comment_runtime import run_customer_reply_v2_comment as _comment

    return await _comment(
        tenant_id=tenant_id,
        comment_text=comment_text,
        detected_language=detected_language,
        response_language=response_language,
        channel=channel,
        asset_id=asset_id,
        provider_sender_id=provider_sender_id,
        provider_display_name=provider_display_name,
        caption=caption,
        media_type=media_type,
        parent_comment=parent_comment,
        image_urls=image_urls,
        media_id=media_id,
        comments_enabled=comments_enabled,
        comment_context=comment_context,
        scripted_retrieval=scripted_retrieval,
        fixture_answer=fixture_answer,
        injected_media_cache=injected_media_cache,
        comment_id=comment_id,
        post_id=post_id,
    )
