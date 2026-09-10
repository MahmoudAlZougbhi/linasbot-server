"""TikTok comment display context. Vision/Luna helpers are removed with the old engine."""

from __future__ import annotations

from typing import Any


def tiktok_video_source(row: Any) -> str:
    for attr in ("video_url", "download_url", "media_url"):
        value = str(getattr(row, attr, "") or "").strip()
        if value.startswith("https://"):
            return value
    return ""


async def build_tiktok_comment_context(
    *,
    tenant_id: str,
    comment_text: str,
    comment_id: str,
    video_id: str,
    caption: str = "",
    thumbnail_url: str = "",
    video_url: str = "",
) -> dict[str, Any]:
    _ = (tenant_id, thumbnail_url, video_url)
    return {
        "comment_text": comment_text,
        "caption": caption,
        "platform": "tiktok",
        "comment_id": comment_id,
        "post_id": video_id,
        "media_type": "video",
        "media_status": "caption_only" if caption else "missing",
        "video_transcript": "",
        "frame_count": 0,
        "tiktok_raw_video": bool(video_url),
        "image_inputs": [],
        "image_urls": [thumbnail_url] if thumbnail_url else [],
    }
