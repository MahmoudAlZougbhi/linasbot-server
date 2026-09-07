"""Build comment vision context for TikTok: caption, cover, frames, and full audio."""

from __future__ import annotations

import base64
from typing import Any

from services.customer_reply_v2.inbound_fetch import MAX_IMAGE_BYTES, fetch_inbound_url
from services.customer_reply_v2.inbound_video_comment import attach_comment_video_frames
from services.customer_reply_v2.media_context import build_comment_media_context, media_context_to_dict


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
    image_inputs: list[dict[str, str]] = []
    media_status = "missing"
    graph_error = ""
    if thumbnail_url:
        fetched = await fetch_inbound_url(thumbnail_url, max_bytes=MAX_IMAGE_BYTES)
        if fetched.get("ok") and fetched.get("bytes"):
            b64 = base64.b64encode(fetched["bytes"]).decode("ascii")
            image_inputs.append({"url": f"data:image/jpeg;base64,{b64}", "kind": "image"})
            media_status = "available"
        else:
            graph_error = str(fetched.get("error") or "tiktok_thumb_fetch_failed")
            media_status = "caption_only" if caption else "failed"
    elif caption:
        media_status = "caption_only"

    extra: dict[str, Any] = {}
    if video_url:
        extra = await attach_comment_video_frames(
            tenant_id=tenant_id,
            media_revision=f"tt:{video_id}",
            video_url=video_url,
            image_inputs=image_inputs,
        )
        image_inputs = list(extra.get("image_inputs") or image_inputs)
        if extra.get("frame_count"):
            media_status = "available"

    ctx = build_comment_media_context(
        tenant_id=tenant_id,
        comment_text=comment_text,
        caption=caption,
        media_type="video",
        image_urls=[thumbnail_url] if thumbnail_url else [],
        media_id=video_id,
        media_revision=f"tt:{video_id}",
        media_status=media_status,
        post_id=video_id,
        image_inputs=image_inputs,
        saw_visuals=bool(image_inputs),
    )
    out = media_context_to_dict(ctx, for_model=True)
    out["comment_text"] = comment_text
    out["platform"] = "tiktok"
    out["comment_id"] = comment_id
    out["post_id"] = video_id
    out["video_transcript"] = str(extra.get("transcript") or out.get("video_transcript") or "")
    out["video_status"] = str(extra.get("video_status") or "")
    out["frame_count"] = int(extra.get("frame_count") or 0)
    out["graph_error"] = graph_error
    out["tiktok_raw_video"] = bool(video_url)
    if not video_url:
        out["video_raw_unavailable"] = "tiktok_official_mp4_missing"
    return out
