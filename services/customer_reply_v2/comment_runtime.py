"""Customer comment reply facade. Auto-reply is off until the new engine lands."""

from __future__ import annotations

from typing import Any

from services.customer_reply_v2.models import ENGINE_REMOVED, CustomerReplyOutcome


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
    _ = (
        tenant_id,
        comment_text,
        detected_language,
        response_language,
        channel,
        asset_id,
        provider_sender_id,
        provider_display_name,
        caption,
        media_type,
        parent_comment,
        image_urls,
        media_id,
        comments_enabled,
        comment_context,
        scripted_retrieval,
        fixture_answer,
        injected_media_cache,
        comment_id,
        post_id,
    )
    if not comments_enabled:
        return CustomerReplyOutcome(stop=True, reason="comments_toggle_off", reply=None)
    return CustomerReplyOutcome(
        stop=True,
        reply=None,
        reason=ENGINE_REMOVED,
        evidence_status="policy_stop",
        metadata={"ai_called": False, "cost_status": "none", "customer_engine": "removed"},
    )
