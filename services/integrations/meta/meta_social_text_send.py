"""Meta DM text send plus optional product-media follow-up (separate HA purpose)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from services.integrations.meta.meta_messaging import MetaMessagingAdapter

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
            from services.brain.reply.product_media_outbound import send_pending_product_media

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
            from services.brain.reply.setup_resource_outbound import send_pending_setup_resources

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
    outbound_text = str(message_text or "").strip()
    if not outbound_text:
        return {"success": False, "skipped": True, "error": "empty_text"}

    if inbound_event_id:
        from services.integrations.meta.meta_controlled_evidence import meta_evidence_surface
        from services.integrations.meta.meta_outbound_attempts import (
            current_meta_outbound_send_purpose,
            execute_guarded_meta_send,
        )

        text_result = await execute_guarded_meta_send(
            event_id=inbound_event_id,
            surface=meta_evidence_surface(kind="meta_dm", channel=channel),
            binding_id=binding_id,
            purpose=current_meta_outbound_send_purpose(),
            send=lambda: adapter.send_text_message(sender_id, outbound_text),
        )
    else:
        text_result = await adapter.send_text_message(sender_id, outbound_text)

    from services.brain.reply.product_media_outbound import send_pending_product_media

    media_result = await send_pending_product_media(
        user_data=user_data,
        sender_id=sender_id,
        adapter=adapter,
        inbound_event_id=inbound_event_id,
        channel=channel,
        binding_id=binding_id,
        capture_send=None,
    )
    from services.brain.reply.setup_resource_outbound import send_pending_setup_resources

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
