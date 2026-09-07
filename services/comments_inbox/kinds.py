"""Normalize Graph / TikTok media types for the operator grid."""

from __future__ import annotations


def media_kind(media_type: str, *, platform: str = "") -> str:
    raw = str(media_type or "").strip().upper()
    plat = str(platform or "").strip().lower()
    if raw in {"REEL", "REELS"}:
        return "reel"
    if raw in {"VIDEO"}:
        return "reel" if plat == "instagram" else "video"
    if raw in {"IMAGE", "CAROUSEL", "CAROUSEL_ALBUM", "PHOTO"}:
        return "post"
    if plat == "tiktok":
        return "video"
    if plat == "facebook":
        return "post"
    return "post"
