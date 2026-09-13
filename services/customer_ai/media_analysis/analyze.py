"""One-shot image/video analysis for comments and inbound customer media."""

from __future__ import annotations

import asyncio
from typing import Any

from services.customer_ai.media_analysis.cache import acquire_lock, get_analysis, put_analysis, release_lock
from services.customer_ai.media_analysis.describe import describe_stills
from services.customer_reply_v2.inbound_fetch import VIDEO_FETCH_TIMEOUT_S, fetch_inbound_url, max_bytes_for_kind
from services.customer_reply_v2.inbound_stt_chunks import transcribe_full_wav
from services.customer_reply_v2.inbound_video import extract_bounded_video


def is_video_media_type(media_type: str) -> bool:
    label = (media_type or "").strip().upper()
    return label in {"VIDEO", "REEL", "STORY"} or "VIDEO" in label or "REEL" in label


def _empty(*, status: str, **extra: Any) -> dict[str, Any]:
    row = {
        "status": status,
        "transcript": "",
        "visual_description": "",
        "duration_s": 0.0,
        "analyze_duration_s": 0.0,
        "frame_count": 0,
        "interval_s": 0.0,
        "truncated": False,
        "kind": "",
    }
    row.update(extra)
    return row


async def analyze_post_media(
    *,
    tenant_id: str,
    post_id: str,
    media_type: str = "",
    urls: list[str] | None = None,
    video_url: str = "",
    caption: str = "",
) -> dict[str, Any]:
    """Analyze a post/reel once. Later comments reuse the cached text."""
    _ = caption
    tid = (tenant_id or "").strip()
    pid = (post_id or "").strip()
    if not tid or not pid:
        return _empty(status="skipped_no_id")
    cached = get_analysis(tenant_id=tid, post_id=pid)
    if cached:
        return {**cached, "cache_hit": True}
    if not acquire_lock(tenant_id=tid, post_id=pid):
        for _attempt in range(25):
            await asyncio.sleep(0.4)
            cached = get_analysis(tenant_id=tid, post_id=pid)
            if cached:
                return {**cached, "cache_hit": True}
    try:
        cached = get_analysis(tenant_id=tid, post_id=pid)
        if cached:
            return {**cached, "cache_hit": True}
        result = await _run(tenant_id=tid, media_type=media_type, urls=list(urls or []), video_url=video_url)
        put_analysis(tenant_id=tid, post_id=pid, payload=result)
        return result
    finally:
        release_lock(tenant_id=tid, post_id=pid)


async def analyze_inbound_video(*, tenant_id: str, blob: bytes) -> dict[str, Any]:
    extracted = extract_bounded_video(blob)
    return await _from_extracted(tenant_id=tenant_id, extracted=extracted, kind="video")


async def analyze_inbound_image(*, tenant_id: str, blob: bytes) -> dict[str, Any]:
    if not blob:
        return _empty(status="empty_image", kind="image")
    visual = await describe_stills([blob], tenant_id=tenant_id, kind="image")
    status = "ok" if visual else "empty"
    return _empty(status=status, kind="image", visual_description=visual)


async def _run(*, tenant_id: str, media_type: str, urls: list[str], video_url: str) -> dict[str, Any]:
    candidates = [str(item).strip() for item in ([video_url, *urls]) if str(item).strip()]
    if not candidates:
        return _empty(status="no_media")
    videoish = is_video_media_type(media_type) or bool(video_url)
    if videoish:
        fetched = await _fetch_first(candidates, kind="video")
        if fetched:
            mime = str(fetched.get("mime") or "")
            blob = fetched.get("bytes") or b""
            if mime.startswith("image/"):
                visual = await describe_stills([blob], tenant_id=tenant_id, kind="video_cover")
                return _empty(status="ok" if visual else "empty", kind="video_cover", visual_description=visual)
            extracted = extract_bounded_video(blob)
            return await _from_extracted(tenant_id=tenant_id, extracted=extracted, kind="video")
        cover = await _fetch_first(candidates, kind="image")
        if cover and cover.get("bytes"):
            visual = await describe_stills([cover["bytes"]], tenant_id=tenant_id, kind="video_cover")
            return _empty(status="ok" if visual else "empty", kind="video_cover", visual_description=visual)
        return _empty(status="fetch_failed", kind="video")
    fetched = await _fetch_first(candidates, kind="image")
    if not fetched or not fetched.get("bytes"):
        return _empty(status="fetch_failed", kind="image")
    visual = await describe_stills([fetched["bytes"]], tenant_id=tenant_id, kind="image")
    return _empty(status="ok" if visual else "empty", kind="image", visual_description=visual)


async def _from_extracted(*, tenant_id: str, extracted: dict[str, Any], kind: str) -> dict[str, Any]:
    status = str(extracted.get("status") or "")
    frames = list(extracted.get("frames") or [])
    audio = extracted.get("audio")
    transcript = ""
    if audio:
        spoken = await transcribe_full_wav(audio)
        if spoken.get("ok"):
            transcript = str(spoken.get("text") or "").strip()
    visual = await describe_stills(frames, tenant_id=tenant_id, kind=kind) if frames else ""
    ok = bool(transcript or visual)
    return {
        "status": "ok" if ok else (status or "empty"),
        "transcript": transcript,
        "visual_description": visual,
        "duration_s": float(extracted.get("duration_s") or 0.0),
        "analyze_duration_s": float(extracted.get("analyze_duration_s") or 0.0),
        "frame_count": int(extracted.get("frame_count") or 0),
        "interval_s": float(extracted.get("interval_s") or 0.0),
        "truncated": bool(extracted.get("truncated")),
        "kind": kind,
    }


async def _fetch_first(urls: list[str], *, kind: str) -> dict[str, Any] | None:
    timeout = VIDEO_FETCH_TIMEOUT_S if kind == "video" else None
    for url in urls:
        fetched = await fetch_inbound_url(url, max_bytes=max_bytes_for_kind(kind), timeout_s=timeout)
        if fetched.get("ok") and fetched.get("bytes"):
            return fetched
    return None
