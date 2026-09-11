"""Customer comment reply facade. Delegates to Customer Brain when enabled."""

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
    from services.customer_ai.flags import customer_brain_enabled
    from services.customer_ai.runtime import run_customer_ai_comment

    if not comments_enabled:
        return CustomerReplyOutcome(stop=True, reason="comments_toggle_off", reply=None)
    if not customer_brain_enabled():
        return CustomerReplyOutcome(
            stop=True,
            reply=None,
            reason=ENGINE_REMOVED,
            evidence_status="policy_stop",
            metadata={"ai_called": False, "cost_status": "none", "customer_engine": "removed"},
        )
    context = comment_context if isinstance(comment_context, dict) else {}
    from services.customer_ai.history_ids import conversation_id_for_brain

    thread = conversation_id_for_brain(payload=context) or str(
        context.get("thread_id") or comment_id or post_id or ""
    )
    return await run_customer_ai_comment(
        tenant_id=tenant_id,
        comment_text=comment_text,
        conversation_id=thread,
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
