"""Attach cached post media analysis onto a comment Brain turn."""

from __future__ import annotations

from typing import Any

from services.brain.media.analyze import analyze_post_media


def merge_comment_media_fields(analysis: dict[str, Any], ctx: dict[str, Any] | None = None) -> dict[str, Any]:
    """Prefer analysis; fall back to TikTok/Meta context fields Terra already reads."""
    out = dict(analysis or {})
    blob = ctx if isinstance(ctx, dict) else {}
    if not str(out.get("post_visual_description") or "").strip():
        visual = str(blob.get("visual_description") or blob.get("post_visual_description") or "").strip()
        if visual:
            out["post_visual_description"] = visual
    if not str(out.get("post_transcript") or "").strip():
        transcript = str(blob.get("video_transcript") or blob.get("post_transcript") or "").strip()
        if transcript:
            out["post_transcript"] = transcript
    if not int(out.get("post_media_frame_count") or 0):
        frames = int(blob.get("frame_count") or blob.get("post_media_frame_count") or 0)
        if frames:
            out["post_media_frame_count"] = frames
    if not str(out.get("post_media_analysis_status") or "").strip() and blob:
        out["post_media_analysis_status"] = str(blob.get("media_status") or blob.get("context_level") or "")
    return out


async def analysis_fields_for_comment(
    *,
    tenant_id: str,
    post_id: str,
    media_type: str = "",
    urls: list[str] | None = None,
    video_url: str = "",
    caption: str = "",
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not (tenant_id or "").strip() or not (post_id or "").strip():
        return merge_comment_media_fields({}, context)
    row = await analyze_post_media(
        tenant_id=tenant_id,
        post_id=post_id,
        media_type=media_type,
        urls=urls,
        video_url=video_url,
        caption=caption,
    )
    fields = {
        "post_transcript": str(row.get("transcript") or "").strip(),
        "post_visual_description": str(row.get("visual_description") or "").strip(),
        "post_media_duration_s": float(row.get("duration_s") or 0.0),
        "post_media_truncated": bool(row.get("truncated")),
        "post_media_analysis_status": str(row.get("status") or ""),
        "post_media_cache_hit": bool(row.get("cache_hit")),
        "post_media_frame_count": int(row.get("frame_count") or 0),
    }
    return merge_comment_media_fields(fields, context)
