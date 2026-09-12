"""Route a saved Live Chat operator text to the correct channel adapter."""

from __future__ import annotations

from typing import Any

from services.live_chat_channel import is_web_live_chat_user, resolve_live_chat_channel
from services.live_chat_operator_social_delivery import is_social_live_chat_user
from services.live_chat_operator_web_delivery import (
    deliver_web_operator_text,
    web_operator_media_not_supported,
)
from services.live_chat_tiktok_operator import is_tiktok_live_chat_user, tiktok_operator_media_not_supported


def operator_media_not_supported(user_id: str, message_type: str) -> dict[str, Any] | None:
    """Explicit block for channels that cannot send operator media. None = allowed."""
    if message_type not in {"voice", "image"}:
        return None
    if is_tiktok_live_chat_user(user_id):
        return tiktok_operator_media_not_supported()
    if is_web_live_chat_user(user_id):
        return web_operator_media_not_supported()
    channel = resolve_live_chat_channel(user_id)
    if channel in {"whatsapp", "instagram", "facebook"}:
        return None
    return {
        "success": False,
        "delivered": False,
        "error": "unknown_channel",
        "channel": channel or "unknown",
    }


async def deliver_saved_operator_text(
    *,
    tenant_id: str | None,
    user_id: str,
    canonical_user_id: str,
    conversation_id: str,
    text: str,
    adapter: Any,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Deliver text already saved to Firestore. Honest failure; never mis-route to WhatsApp."""
    if is_web_live_chat_user(user_id):
        return deliver_web_operator_text(
            user_id=user_id,
            conversation_id=conversation_id,
            text=text,
            idempotency_key=idempotency_key,
        )
    if is_social_live_chat_user(user_id):
        from services.live_chat_operator_social_delivery import deliver_social_operator_text

        delivery = await deliver_social_operator_text(
            tenant_id=tenant_id,
            user_id=user_id,
            conversation_id=conversation_id,
            text=text,
        )
        if delivery is None:
            return {"success": False, "delivered": False, "error": "social_delivery_failed"}
        return delivery

    channel = resolve_live_chat_channel(user_id)
    if channel != "whatsapp":
        return {
            "success": False,
            "delivered": False,
            "error": "unknown_channel",
            "channel": channel or "unknown",
        }

    try:
        result = await adapter.send_text_message(canonical_user_id, text)
    except Exception as send_error:
        return {
            "success": False,
            "delivered": False,
            "error": str(send_error),
            "channel": "whatsapp",
        }
    if not isinstance(result, dict) or not result.get("success"):
        send_err = (
            str((result or {}).get("error") or "send failed") if isinstance(result, dict) else "send failed"
        )
        return {
            "success": False,
            "delivered": False,
            "error": send_err,
            "channel": "whatsapp",
        }
    return {"success": True, "delivered": True, "channel": "whatsapp", **result}
