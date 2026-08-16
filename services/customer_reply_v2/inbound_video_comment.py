"""Attach bounded video frames to comment context (not thumbnail-only)."""

from __future__ import annotations

import base64
from typing import Any

from services.customer_reply_v2.inbound_fetch import MAX_VIDEO_BYTES, fetch_inbound_url
from services.customer_reply_v2.inbound_stt import transcribe_inbound_audio
from services.customer_reply_v2.inbound_video import extract_bounded_video
from services.customer_reply_v2.media_context import MAX_VIDEO_FRAMES, save_cached_media


def ig_video_source(payload: dict[str, Any] | None) -> str:
    raw = payload if isinstance(payload, dict) else {}
    media_type = str(raw.get("media_type") or "").strip().upper()
    if media_type not in {"VIDEO", "REELS", "REEL"}:
        return ""
    return str(raw.get("media_url") or "").strip()


async def attach_comment_video_frames(
    *,
    tenant_id: str,
    media_revision: str,
    video_url: str,
    image_inputs: list[dict[str, str]],
    transcribe: bool = True,
) -> dict[str, Any]:
    """Download a video once, extract ≤3 frames + optional audio transcript."""
    if not video_url:
        return {"image_inputs": image_inputs, "video_status": "", "transcript": ""}
    fetched = await fetch_inbound_url(video_url, max_bytes=MAX_VIDEO_BYTES)
    if not fetched.get("ok"):
        return {
            "image_inputs": image_inputs,
            "video_status": str(fetched.get("error") or "video_fetch_failed"),
            "transcript": "",
        }
    extracted = extract_bounded_video(fetched.get("bytes") or b"")
    frames = list(extracted.get("frames") or [])[:MAX_VIDEO_FRAMES]
    extra: list[dict[str, str]] = []
    for frame in frames:
        b64 = base64.b64encode(frame).decode("ascii")
        extra.append({"url": f"data:image/jpeg;base64,{b64}", "kind": "video_frame"})
    transcript = ""
    audio = extracted.get("audio")
    if transcribe and audio:
        spoken = await transcribe_inbound_audio(data=audio, filename="comment_video.wav")
        if spoken.get("ok"):
            transcript = str(spoken.get("text") or "").strip()
    merged = list(image_inputs) + extra
    save_cached_media(
        tenant_id,
        media_revision,
        {
            "media_type": "video",
            "visual_summary": transcript,
            "frame_count": len(extra),
            "frame_urls": [],
        },
    )
    return {
        "image_inputs": merged,
        "video_status": str(extracted.get("status") or ""),
        "transcript": transcript,
        "frame_count": len(extra),
    }
