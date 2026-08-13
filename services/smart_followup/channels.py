"""Smart Follow-Up channel identifiers and adapter routing."""

from __future__ import annotations

from typing import TYPE_CHECKING

from services.requests.constants import (
    SOURCE_CHANNEL_FACEBOOK_MESSENGER,
    SOURCE_CHANNEL_INSTAGRAM_DM,
    SOURCE_CHANNEL_WHATSAPP_CLOUD,
)

if TYPE_CHECKING:
    from services.smart_followup.adapters.base import SmartFollowUpChannelAdapter

SUPPORTED_CHANNELS = frozenset(
    {
        SOURCE_CHANNEL_WHATSAPP_CLOUD,
        SOURCE_CHANNEL_INSTAGRAM_DM,
        SOURCE_CHANNEL_FACEBOOK_MESSENGER,
    }
)


def normalize_followup_channel(channel: str | None) -> str:
    raw = str(channel or "").strip().lower()
    if raw in {SOURCE_CHANNEL_WHATSAPP_CLOUD, "whatsapp", "whatsapp_dm"}:
        return SOURCE_CHANNEL_WHATSAPP_CLOUD
    if raw in {SOURCE_CHANNEL_INSTAGRAM_DM, "instagram"}:
        return SOURCE_CHANNEL_INSTAGRAM_DM
    if raw in {
        SOURCE_CHANNEL_FACEBOOK_MESSENGER,
        "facebook",
        "facebook_dm",
        "messenger",
        "page",
    }:
        return SOURCE_CHANNEL_FACEBOOK_MESSENGER
    raise ValueError(f"unsupported_followup_channel:{raw or 'empty'}")


def meta_platform_for_channel(channel: str) -> str:
    normalized = normalize_followup_channel(channel)
    if normalized == SOURCE_CHANNEL_INSTAGRAM_DM:
        return "instagram"
    if normalized == SOURCE_CHANNEL_FACEBOOK_MESSENGER:
        return "facebook"
    raise ValueError(f"not_meta_channel:{channel}")


def get_channel_adapter(channel: str) -> SmartFollowUpChannelAdapter:
    normalized = normalize_followup_channel(channel)
    if normalized == SOURCE_CHANNEL_WHATSAPP_CLOUD:
        from services.smart_followup.adapters.whatsapp import WhatsAppFollowUpAdapter

        return WhatsAppFollowUpAdapter()
    from services.smart_followup.adapters.meta_dm import MetaDmFollowUpAdapter

    return MetaDmFollowUpAdapter(channel=normalized)
