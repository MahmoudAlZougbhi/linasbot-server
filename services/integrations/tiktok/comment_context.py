"""TikTok comment display context — caption, cover fetch, optional official MP4."""

from __future__ import annotations

import base64
from typing import Any

from services.brain.reply.inbound_fetch import MAX_IMAGE_BYTES, fetch_inbound_url

__all__ = ["build_tiktok_comment_context", "fetch_inbound_url", "tiktok_video_source"]


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
    _ = (comment_text, comment_id)
    image_inputs: list[dict[str, str]] = []
    media_status = "missing"
    if thumbnail_url:
        fetched = await fetch_inbound_url(thumbnail_url, max_bytes=MAX_IMAGE_BYTES)
        if fetched.get("ok") and fetched.get("bytes"):
            b64 = base64.b64encode(fetched["bytes"]).decode("ascii")
            image_inputs.append({"url": f"data:image/jpeg;base64,{b64}", "kind": "image"})
            media_status = "available"
        else:
            media_status = "caption_only" if caption else "failed"
    elif caption:
        media_status = "caption_only"

    official_url = str(video_url or "").strip()
    tiktok_raw_video = official_url.startswith("https://")
    out: dict[str, Any] = {
        "comment_text": comment_text,
        "caption": caption,
        "platform": "tiktok",
        "comment_id": comment_id,
        "post_id": video_id,
        "media_type": "video",
        "media_status": media_status,
        "video_transcript": "",
        "frame_count": 0,
        "tiktok_raw_video": tiktok_raw_video,
        "image_inputs": image_inputs,
        "image_urls": [thumbnail_url] if thumbnail_url else [],
        "image_input_count": len(image_inputs),
    }
    if official_url:
        out["video_url"] = official_url
        analysis = await _tiktok_video_analysis(
            tenant_id=tenant_id,
            video_id=video_id,
            video_url=official_url,
            caption=caption,
            thumbnail_url=thumbnail_url,
        )
        out["video_transcript"] = str(analysis.get("post_transcript") or "")
        out["visual_description"] = str(analysis.get("post_visual_description") or "")
        out["frame_count"] = int(analysis.get("post_media_frame_count") or 0)
        out["post_media_analysis_status"] = str(analysis.get("post_media_analysis_status") or "")
    if not tiktok_raw_video:
        out["video_raw_unavailable"] = "tiktok_official_mp4_missing"
    return out


async def _tiktok_video_analysis(
    *,
    tenant_id: str,
    video_id: str,
    video_url: str,
    caption: str,
    thumbnail_url: str,
) -> dict[str, Any]:
    try:
        from services.brain.media.comment_attach import analysis_fields_for_comment

        return await analysis_fields_for_comment(
            tenant_id=tenant_id,
            post_id=video_id,
            media_type="VIDEO",
            urls=[thumbnail_url] if thumbnail_url else None,
            video_url=video_url,
            caption=caption,
        )
    except Exception:
        return {}
