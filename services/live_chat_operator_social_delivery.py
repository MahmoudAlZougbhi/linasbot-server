"""Route Live Chat operator outbound to Meta / TikTok instead of WhatsApp."""

from __future__ import annotations

from typing import Any

from services.live_chat_meta_operator import (
    deliver_live_chat_meta_operator_text,
    is_meta_dm_live_chat_user,
    parse_meta_live_chat_user_id,
)
from services.live_chat_meta_operator_media import (
    decode_operator_media_payload,
    deliver_live_chat_meta_operator_media,
)
from services.live_chat_tiktok_operator import (
    deliver_live_chat_tiktok_operator_text,
    is_tiktok_live_chat_user,
    tiktok_operator_media_not_supported,
)
from services.requests.constants import (
    SOURCE_CHANNEL_FACEBOOK_MESSENGER,
    SOURCE_CHANNEL_INSTAGRAM_DM,
    SOURCE_CHANNEL_WHATSAPP_CLOUD,
)


def is_social_live_chat_user(user_id: str | None) -> bool:
    return is_meta_dm_live_chat_user(user_id) or is_tiktok_live_chat_user(user_id)


def infer_live_chat_source_channel(user_id: str | None, explicit: str | None = None) -> str | None:
    """Resolve Requests source_channel so Meta/TikTok threads never open WhatsApp Postgres."""
    if explicit and str(explicit).strip():
        return str(explicit).strip().lower()
    uid = str(user_id or "")
    if is_meta_dm_live_chat_user(uid):
        channel, _sender, _asset, _tenant = parse_meta_live_chat_user_id(uid)
        if channel == "facebook":
            return SOURCE_CHANNEL_FACEBOOK_MESSENGER
        return SOURCE_CHANNEL_INSTAGRAM_DM
    if is_tiktok_live_chat_user(uid):
        return "tiktok"
    return None


def live_chat_needs_whatsapp_session(
    *,
    user_id: str | None,
    tenant_id: str | None,
    source_channel: str | None,
) -> bool:
    if not str(tenant_id or "").strip():
        return False
    channel = infer_live_chat_source_channel(user_id, source_channel)
    if channel == SOURCE_CHANNEL_WHATSAPP_CLOUD:
        return True
    if is_social_live_chat_user(user_id):
        return False
    return True


async def deliver_social_operator_text(
    *,
    tenant_id: str | None,
    user_id: str,
    conversation_id: str,
    text: str,
) -> dict[str, Any] | None:
    from services.queues.config import redis_required

    if is_meta_dm_live_chat_user(user_id):
        return await deliver_live_chat_meta_operator_text(
            tenant_id=tenant_id,
            user_id=user_id,
            text=text,
        )
    if is_tiktok_live_chat_user(user_id):
        if redis_required():
            return _enqueue_operator_text(
                tenant_id=tenant_id, user_id=user_id, conversation_id=conversation_id, text=text
            )
        return await deliver_live_chat_tiktok_operator_text(
            tenant_id=tenant_id,
            user_id=user_id,
            conversation_id=conversation_id,
            text=text,
        )
    return None


def _enqueue_operator_text(*, tenant_id: str | None, user_id: str, conversation_id: str, text: str) -> dict[str, Any]:
    from services.omnichannel.operator_enqueue import enqueue_operator_reply

    if is_meta_dm_live_chat_user(user_id):
        from services.live_chat_meta_operator import parse_meta_live_chat_user_id, resolve_meta_live_chat_tenant

        channel, sender_id, asset_id, _embedded = parse_meta_live_chat_user_id(user_id)
        tenant = resolve_meta_live_chat_tenant(tenant_id, user_id)
        return enqueue_operator_reply(
            tenant_id=tenant,
            channel=channel,
            surface="operator",
            account_id=str(asset_id or ""),
            conversation_key=f"{tenant}:{channel}:{sender_id}",
            text=text,
        )
    from services.live_chat_tiktok_operator import parse_tiktok_live_chat_user_id

    sender_id, connection_id, embedded_tenant = parse_tiktok_live_chat_user_id(user_id)
    tenant = str(tenant_id or embedded_tenant or "linas").strip()
    return enqueue_operator_reply(
        tenant_id=tenant,
        channel="tiktok",
        surface="operator",
        account_id=str(connection_id or ""),
        conversation_key=f"{tenant}:tiktok:{conversation_id or sender_id}",
        text=text,
    )


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
