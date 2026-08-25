"""Route Live Chat operator outbound to Meta / TikTok instead of WhatsApp."""

from __future__ import annotations

from typing import Any

from services.live_chat_meta_operator import deliver_live_chat_meta_operator_text, is_meta_dm_live_chat_user
from services.live_chat_meta_operator_media import (
    decode_operator_media_payload,
    deliver_live_chat_meta_operator_media,
)
from services.live_chat_tiktok_operator import (
    deliver_live_chat_tiktok_operator_text,
    is_tiktok_live_chat_user,
    tiktok_operator_media_not_supported,
)


def is_social_live_chat_user(user_id: str | None) -> bool:
    return is_meta_dm_live_chat_user(user_id) or is_tiktok_live_chat_user(user_id)


async def deliver_social_operator_text(
    *,
    tenant_id: str | None,
    user_id: str,
    conversation_id: str,
    text: str,
) -> dict[str, Any] | None:
    if is_meta_dm_live_chat_user(user_id):
        return await deliver_live_chat_meta_operator_text(
            tenant_id=tenant_id,
            user_id=user_id,
            text=text,
        )
    if is_tiktok_live_chat_user(user_id):
        return await deliver_live_chat_tiktok_operator_text(
            tenant_id=tenant_id,
            user_id=user_id,
            conversation_id=conversation_id,
            text=text,
        )
    return None


async def deliver_social_operator_media(
    *,
    tenant_id: str | None,
    user_id: str,
    payload: str | None = None,
    media_bytes: bytes | None = None,
    mime: str,
    filename: str,
) -> dict[str, Any] | None:
    if is_tiktok_live_chat_user(user_id):
        return tiktok_operator_media_not_supported()
    if not is_meta_dm_live_chat_user(user_id):
        return None
    raw = media_bytes if media_bytes is not None else decode_operator_media_payload(payload or "")
    return await deliver_live_chat_meta_operator_media(
        tenant_id=tenant_id,
        user_id=user_id,
        media_bytes=raw,
        mime=mime,
        filename=filename,
    )
