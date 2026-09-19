"""Requests capture helpers: channel mapping for persist. No customer copy."""

from __future__ import annotations

from services.requests.constants import SOURCE_CHANNELS

_CHANNEL_TO_SOURCE: dict[str, str] = {
    "instagram": "instagram_dm",
    "instagram_dm": "instagram_dm",
    "facebook": "facebook_messenger",
    "facebook_dm": "facebook_messenger",
    "facebook_messenger": "facebook_messenger",
    "messenger": "facebook_messenger",
    "page": "facebook_messenger",
    "whatsapp": "whatsapp_cloud",
    "whatsapp_cloud": "whatsapp_cloud",
    "wa": "whatsapp_cloud",
    "comment_linked_dm": "comment_linked_dm",
    "instagram_comment": "comment_linked_dm",
    "facebook_comment": "comment_linked_dm",
    "ig_comment": "comment_linked_dm",
    "fb_comment": "comment_linked_dm",
    "tiktok_comment": "comment_linked_dm",
    "comment": "comment_linked_dm",
    "web": "web_chat",
    "web_chat": "web_chat",
    "website": "web_chat",
    "website_chat": "web_chat",
}


def normalize_source_channel(channel: str | None) -> str | None:
    raw = str(channel or "").strip().lower()
    if not raw:
        return None
    mapped = _CHANNEL_TO_SOURCE.get(raw, raw)
    if mapped in SOURCE_CHANNELS:
        return mapped
    return None
