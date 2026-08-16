"""Meta DM text send plus optional product-media follow-up (separate HA purpose)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from services.meta_messaging import MetaMessagingAdapter

SendFunc = Callable[..., Awaitable[Any]]


async def send_meta_social_outbound(
    *,
    namespaced_id: str,
    message_text: str | None,
    image_url: str | None,
    audio_url: str | None,
    capture_send: SendFunc | None,
    adapter: MetaMessagingAdapter | None,
    inbound_event_id: str | None,
    channel: str,
    binding_id: str,
    sender_id: str,
    user_data: dict[str, Any],
) -> Any:
    _ = image_url, audio_url
    if capture_send is not None:
        await capture_send(namespaced_id, message_text, image_url, audio_url)
        if message_text:
            from services.customer_reply_v2.product_media_outbound import send_pending_product_media

            await send_pending_product_media(
                user_data=user_data,
                sender_id=sender_id,
                adapter=None,
                inbound_event_id=inbound_event_id,
                channel=channel,
                binding_id=binding_id,
                capture_send=capture_send,
                capture_to=namespaced_id,
            )
            from services.customer_reply_v2.setup_resource_outbound import send_pending_setup_resources

            await send_pending_setup_resources(
                user_data=user_data,
                sender_id=sender_id,
                adapter=None,
                inbound_event_id=inbound_event_id,
                channel=channel,
                binding_id=binding_id,
                capture_send=capture_send,
                capture_to=namespaced_id,
            )
        return {"success": True, "simulated": True, "delivered_externally": False}
    if adapter is None:
        return {"success": False, "error": "Meta adapter unavailable"}
    if not message_text:
        return {"success": False, "error": "Only text replies are enabled for Meta social DMs"}

    if inbound_event_id:
        from services.meta_controlled_evidence import meta_evidence_surface
        from services.meta_outbound_attempts import (
            current_meta_outbound_send_purpose,
            execute_guarded_meta_send,
        )

        text_result = await execute_guarded_meta_send(
            event_id=inbound_event_id,
            surface=meta_evidence_surface(kind="meta_dm", channel=channel),
            binding_id=binding_id,
            purpose=current_meta_outbound_send_purpose(),
            send=lambda: adapter.send_text_message(sender_id, message_text),
        )
    else:
        text_result = await adapter.send_text_message(sender_id, message_text)

    from services.customer_reply_v2.product_media_outbound import send_pending_product_media

    media_result = await send_pending_product_media(
        user_data=user_data,
        sender_id=sender_id,
        adapter=adapter,
        inbound_event_id=inbound_event_id,
        channel=channel,
        binding_id=binding_id,
        capture_send=None,
    )
    from services.customer_reply_v2.setup_resource_outbound import send_pending_setup_resources

    resource_result = await send_pending_setup_resources(
        user_data=user_data,
        sender_id=sender_id,
        adapter=adapter,
        inbound_event_id=inbound_event_id,
        channel=channel,
        binding_id=binding_id,
        capture_send=None,
    )
    if isinstance(text_result, dict):
        text_result = dict(text_result)
        text_result["product_media_delivery"] = media_result
        text_result["setup_resource_delivery"] = resource_result
    return text_result
