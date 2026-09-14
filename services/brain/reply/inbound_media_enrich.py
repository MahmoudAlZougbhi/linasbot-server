"""Attach visual description + full STT onto inbound image/video ingest."""

from __future__ import annotations

from typing import Any

from services.brain.media.describe import describe_stills
from services.brain.reply.inbound_stt_chunks import transcribe_full_wav


async def enrich_inbound_image(*, tenant_id: str, blob: bytes, result: Any, text_parts: list[str]) -> None:
    visual = await describe_stills([blob], tenant_id=tenant_id, kind="image") if blob else ""
    if visual:
        result.extract = visual
        text_parts.append(visual)


async def enrich_inbound_video(
    *,
    tenant_id: str,
    blob: bytes,
    mime: str,
    video_fn: Any,
    result: Any,
    text_parts: list[str],
) -> None:
    _ = mime
    if not blob:
        result.video_status = "video_bytes_unavailable"
        text_parts.append("[Customer sent a video]")
        return
    extracted = video_fn(blob)
    result.video_status = str(extracted.get("status") or "")
    result.video_frame_count = int(extracted.get("frame_count") or 0)
    frames = list(extracted.get("frames") or [])
    if frames and not result.image_media_id:
        from services.products.media import store_product_media

        stored = store_product_media(
            tenant_id=tenant_id,
            user_id="inbound_customer",
            filename="video_frame.jpg",
            content=frames[0],
            content_type="image/jpeg",
        )
        if stored.get("ok"):
            result.image_media_id = str(stored.get("media_id") or "") or None
    audio = extracted.get("audio")
    if audio:
        spoken = await transcribe_full_wav(audio)
        if spoken.get("ok") and spoken.get("text"):
            result.transcript = str(spoken["text"]).strip()
            text_parts.append(result.transcript)
            if tenant_id:
                from services.billing.membership.provider_expense import record_pending_provider

                record_pending_provider(
                    event_id=f"stt:{tenant_id}:video_audio.wav",
                    tenant_id=tenant_id,
                    category="stt",
                    feature="inbound_media",
                    provider="openai",
                    model=str(spoken.get("model") or "stt"),
                    operation_id="video_audio.wav",
                )
        else:
            result.fetch_errors.append(str(spoken.get("error") or "video_stt_failed"))
    visual = await describe_stills(frames, tenant_id=tenant_id, kind="video") if frames else ""
    if visual:
        result.extract = visual
        text_parts.append(visual)
    if not result.transcript and not visual:
        text_parts.append("[Customer sent a video]")
    if result.video_status in {"ffmpeg_unavailable", "video_extract_failed", "empty_video", "video_too_large"}:
        result.fetch_errors.append(result.video_status)
