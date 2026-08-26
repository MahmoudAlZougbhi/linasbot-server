"""Operator outbound text for Instagram / Facebook Live Chat threads."""

from __future__ import annotations

from typing import Any

from services.requests.constants import (
    SOURCE_CHANNEL_FACEBOOK_MESSENGER,
    SOURCE_CHANNEL_INSTAGRAM_DM,
)
from services.requests.delivery import deliver_meta_dm

_META_CHANNELS = frozenset({"instagram", "facebook"})


def is_meta_dm_live_chat_user(user_id: str | None) -> bool:
    try:
        parse_meta_live_chat_user_id(str(user_id or ""))
        return True
    except ValueError:
        return False


def parse_meta_live_chat_user_id(user_id: str) -> tuple[str, str, str | None, str | None]:
    """Return (channel, sender_id, asset_id, embedded_tenant_id)."""
    parts = [p.strip() for p in str(user_id or "").split(":") if p.strip()]
    if len(parts) == 2:
        channel, sender = parts[0].lower(), parts[1]
        if channel in _META_CHANNELS:
            return channel, sender, None, None
    if len(parts) == 3:
        channel, asset, sender = parts[0].lower(), parts[1], parts[2]
        if channel in _META_CHANNELS:
            return channel, sender, asset, None
    if len(parts) >= 4:
        tenant, channel, asset, sender = parts[0], parts[1].lower(), parts[2], parts[3]
        if channel in _META_CHANNELS:
            return channel, sender, asset, tenant
    raise ValueError("unsupported_meta_live_chat_user_id")


def _source_channel_for_meta(channel: str) -> str:
    if channel == "facebook":
        return SOURCE_CHANNEL_FACEBOOK_MESSENGER
    return SOURCE_CHANNEL_INSTAGRAM_DM


def resolve_meta_live_chat_tenant(tenant_id: str | None, user_id: str) -> str:
    """Map Live Chat social user_id formats to the Meta binding tenant."""
    from services.meta_app_registry import normalize_meta_tenant_id

    _, _, _, embedded_tenant = parse_meta_live_chat_user_id(user_id)
    if embedded_tenant:
        try:
            return normalize_meta_tenant_id(embedded_tenant)
        except Exception:
            return str(embedded_tenant).strip().lower()

    parts = [p.strip() for p in str(user_id or "").split(":") if p.strip()]
    if len(parts) in {2, 3} and parts[0].lower() in _META_CHANNELS:
        # compose_social_user_id omits tenant prefix for linas-branded threads.
        return "linas"

    fallback = str(tenant_id or "linas").strip()
    try:
        return normalize_meta_tenant_id(fallback)
    except Exception:
        return fallback.lower()


async def deliver_live_chat_meta_operator_text(
    *,
    tenant_id: str | None,
    user_id: str,
    text: str,
) -> dict[str, Any]:
    channel, sender_id, asset_id, _embedded_tenant = parse_meta_live_chat_user_id(user_id)
    tenant = resolve_meta_live_chat_tenant(tenant_id, user_id)
    if not tenant:
        return {"success": False, "error": "tenant_required_for_meta_send", "delivered": False}

    account = str(asset_id or "").strip()
    if not account:
        from services.meta_app_registry import get_meta_app_registry

        registry = get_meta_app_registry()
        bindings = [
            b
            for b in registry.list_bindings(include_inactive=False)
            if b.tenant_id == tenant and b.channel == channel and b.active
        ]
        if not bindings:
            return {"success": False, "error": "meta_binding_not_found", "delivered": False}
        account = str(bindings[0].asset_id or "").strip()
    if not account:
        return {"success": False, "error": "meta_account_not_found", "delivered": False}

    from services.job_queue import job_queue
    from services.omnichannel.operator_enqueue import enqueue_operator_reply
    from services.queues.config import redis_required

    if redis_required() and getattr(job_queue, "production_ready", False):
        return enqueue_operator_reply(
            tenant_id=tenant,
            channel=channel,
            surface="operator",
            account_id=account,
            conversation_key=f"{tenant}:{channel}:{sender_id}",
            text=text,
        )

    result = await deliver_meta_dm(
        tenant_id=tenant,
        source_channel=_source_channel_for_meta(channel),
        source_account_id=account,
        external_customer_id=sender_id,
        text=text,
    )
    if result.status == "sent":
        return {
            "success": True,
            "delivered": True,
            "provider_message_id": result.provider_message_id,
            "channel": channel,
        }
    return {
        "success": False,
        "delivered": False,
        "error": result.error_redacted or "meta_delivery_failed",
        "blocked": result.status == "blocked",
        "channel": channel,
    }
