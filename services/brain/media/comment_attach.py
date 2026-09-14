"""Attach cached post media analysis onto a comment Brain turn."""

from __future__ import annotations

from typing import Any

from services.brain.media.analyze import analyze_post_media


async def analysis_fields_for_comment(
    *,
    tenant_id: str,
    post_id: str,
    media_type: str = "",
    urls: list[str] | None = None,
    video_url: str = "",
    caption: str = "",
) -> dict[str, Any]:
    if not (tenant_id or "").strip() or not (post_id or "").strip():
        return {}
    row = await analyze_post_media(
        tenant_id=tenant_id,
        post_id=post_id,
        media_type=media_type,
        urls=urls,
        video_url=video_url,
        caption=caption,
    )
    return {
        "post_transcript": str(row.get("transcript") or "").strip(),
        "post_visual_description": str(row.get("visual_description") or "").strip(),
        "post_media_duration_s": float(row.get("duration_s") or 0.0),
        "post_media_truncated": bool(row.get("truncated")),
        "post_media_analysis_status": str(row.get("status") or ""),
        "post_media_cache_hit": bool(row.get("cache_hit")),
        "post_media_frame_count": int(row.get("frame_count") or 0),
    }
