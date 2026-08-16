"""Ingest customer inbound attachments into V2 (image/video/audio/file/link)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from services.customer_reply_v2.inbound_extract import extract_inbound_file
from services.customer_reply_v2.inbound_fetch import fetch_inbound_url, link_host, max_bytes_for_kind
from services.customer_reply_v2.inbound_stt import transcribe_inbound_audio
from services.customer_reply_v2.inbound_video import extract_bounded_video
from services.ssrf_guard import SSRFValidationError, validate_fetch_url

FetchFn = Callable[[str, int], Awaitable[dict[str, Any]]]
TranscribeFn = Callable[..., Awaitable[dict[str, Any]]]
VideoFn = Callable[[bytes], dict[str, Any]]

_PIPELINE_LABELS = {
    "image": "[Customer sent an image]",
    "video": "[Customer sent a video]",
    "audio": "[Customer sent a voice message]",
    "file": "[Customer sent a file]",
    "link": "[Customer sent a link]",
}


@dataclass
class InboundMediaResult:
    attachment_types: list[str] = field(default_factory=list)
    image_media_id: str | None = None
    transcript: str = ""
    extract: str = ""
    video_status: str = ""
    video_frame_count: int = 0
    inbound_link: str = ""
    pipeline_text: str = ""
    safety_blocked: bool = False
    safety_reasons: list[str] = field(default_factory=list)
    fetch_errors: list[str] = field(default_factory=list)
    safety_image_urls: list[str] = field(default_factory=list)


def inbound_payload_from_user_data(user_data: dict[str, Any] | None) -> dict[str, Any]:
    data = user_data if isinstance(user_data, dict) else {}
    inbound = dict(data.get("inbound_media_for_luna") or {})
    urls = data.get("inbound_safety_image_urls")
    if urls:
        inbound["safety_image_urls"] = [str(u) for u in urls if str(u).strip()]
    types = data.get("inbound_attachment_types")
    if types and not inbound.get("attachment_types"):
        inbound["attachment_types"] = [str(t) for t in types if str(t).strip()]
    media_id = str(data.get("inbound_image_media_id") or "").strip()
    if media_id and not inbound.get("image_media_id"):
        inbound["image_media_id"] = media_id
    return inbound


def luna_inbound_view(result: InboundMediaResult) -> dict[str, Any]:
    """Structured inbound for Luna: ids and counts, no bytes/storage keys."""
    return {
        "attachment_types": list(result.attachment_types),
        "image_media_id": result.image_media_id or "",
        "transcript": (result.transcript or "")[:2000],
        "file_extract_preview": (result.extract or "")[:2000],
        "video_frame_count": int(result.video_frame_count or 0),
        "video_status": result.video_status or "",
        "inbound_link": result.inbound_link or "",
        "inbound_link_host": link_host(result.inbound_link),
        "safety_blocked": bool(result.safety_blocked),
    }


def classify_attachment(item: Any) -> str:
    if not isinstance(item, dict):
        return "file" if item else ""
    raw_type = str(item.get("type") or "").strip().lower()
    mime = str(item.get("mime") or item.get("mime_type") or "").strip().lower()
    payload_raw = item.get("payload")
    payload: dict[str, Any] = payload_raw if isinstance(payload_raw, dict) else {}
    mime = mime or str(payload.get("mime_type") or payload.get("mime") or "").strip().lower()
    if raw_type in {"image", "video", "audio", "file"}:
        return raw_type
    if raw_type in {"share", "fallback", "link", "story_mention"}:
        return "link"
    if mime.startswith("image/"):
        return "image"
    if mime.startswith("video/"):
        return "video"
    if mime.startswith("audio/"):
        return "audio"
    url = _attachment_url(item)
    if url and raw_type in {"", "attachment"}:
        return "link"
    return "file" if raw_type or url else ""


def _attachment_url(item: dict[str, Any]) -> str:
    payload_raw = item.get("payload")
    payload: dict[str, Any] = payload_raw if isinstance(payload_raw, dict) else {}
    for key in ("url", "link"):
        value = str(item.get(key) or payload.get(key) or "").strip()
        if value:
            return value
    return ""


def _filename(item: dict[str, Any], kind: str) -> str:
    payload_raw = item.get("payload")
    payload: dict[str, Any] = payload_raw if isinstance(payload_raw, dict) else {}
    name = str(item.get("filename") or payload.get("filename") or payload.get("name") or "").strip()
    if name:
        return name[:180]
    url = _attachment_url(item)
    path = urlparse(url).path if url else ""
    leaf = path.rsplit("/", 1)[-1] if path else ""
    if leaf:
        return leaf[:180]
    return {"image": "inbound.jpg", "video": "inbound.mp4", "audio": "inbound.ogg"}.get(kind, "inbound.bin")


async def ingest_inbound_attachments(
    *,
    tenant_id: str,
    attachments: list[Any] | None,
    caption: str = "",
    fetch_url: FetchFn | None = None,
    transcribe: TranscribeFn | None = None,
    extract_video: VideoFn | None = None,
) -> InboundMediaResult:
    result = InboundMediaResult()
    text_parts = [str(caption or "").strip()] if str(caption or "").strip() else []
    rows = [item for item in (attachments or []) if item]
    if not rows:
        result.pipeline_text = text_parts[0] if text_parts else ""
        return result

    fetcher = fetch_url or (lambda url, max_bytes: fetch_inbound_url(url, max_bytes=max_bytes))
    stt = transcribe or transcribe_inbound_audio
    video_fn = extract_video or extract_bounded_video

    for item in rows:
        kind = classify_attachment(item)
        if not kind:
            continue
        if kind not in result.attachment_types:
            result.attachment_types.append(kind)
        if kind == "link":
            _ingest_link(item, result, text_parts)
            continue
        url = _attachment_url(item) if isinstance(item, dict) else ""
        blob = b""
        mime = ""
        if url:
            fetched = await fetcher(url, max_bytes_for_kind(kind))
            if not fetched.get("ok"):
                result.fetch_errors.append(str(fetched.get("error") or "fetch_failed"))
            else:
                blob = fetched.get("bytes") or b""
                mime = str(fetched.get("mime") or "")
                if kind == "image" and fetched.get("url"):
                    result.safety_image_urls.append(str(fetched["url"]))
        if kind == "image":
            await _ingest_image(
                tenant_id=tenant_id, item=item, blob=blob, mime=mime, result=result, text_parts=text_parts
            )
        elif kind == "audio":
            await _ingest_audio(item=item, blob=blob, stt=stt, result=result, text_parts=text_parts)
        elif kind == "video":
            await _ingest_video(
                tenant_id=tenant_id,
                item=item,
                blob=blob,
                mime=mime,
                video_fn=video_fn,
                stt=stt,
                result=result,
                text_parts=text_parts,
            )
        elif kind == "file":
            _ingest_file(item=item, blob=blob, mime=mime, result=result, text_parts=text_parts)

    if not text_parts:
        for kind in result.attachment_types:
            label = _PIPELINE_LABELS.get(kind)
            if label:
                text_parts.append(label)
                break
    result.pipeline_text = "\n".join(part for part in text_parts if part).strip()
    return result


def _ingest_link(item: dict[str, Any], result: InboundMediaResult, text_parts: list[str]) -> None:
    url = _attachment_url(item)
    if not url:
        result.fetch_errors.append("link_missing_url")
        return
    try:
        normalized = validate_fetch_url(url, allowed_schemes=("https",))
    except SSRFValidationError:
        result.fetch_errors.append("ssrf_blocked:link")
        return
    result.inbound_link = normalized
    text_parts.append(f"[Customer sent a link: {normalized}]")


async def _ingest_image(
    *,
    tenant_id: str,
    item: dict[str, Any],
    blob: bytes,
    mime: str,
    result: InboundMediaResult,
    text_parts: list[str],
) -> None:
    if not blob:
        text_parts.append(_PIPELINE_LABELS["image"])
        return
    from services.products.media import store_product_media

    stored = store_product_media(
        tenant_id=tenant_id,
        user_id="inbound_customer",
        filename=_filename(item, "image"),
        content=blob,
        content_type=mime or "image/jpeg",
    )
    if not stored.get("ok"):
        result.fetch_errors.append(str(stored.get("error") or "image_store_failed"))
        text_parts.append(_PIPELINE_LABELS["image"])
        return
    if not result.image_media_id:
        result.image_media_id = str(stored.get("media_id") or "") or None
    text_parts.append(_PIPELINE_LABELS["image"])


async def _ingest_audio(
    *,
    item: dict[str, Any],
    blob: bytes,
    stt: TranscribeFn,
    result: InboundMediaResult,
    text_parts: list[str],
) -> None:
    if not blob:
        text_parts.append(_PIPELINE_LABELS["audio"])
        return
    spoken = await stt(data=blob, filename=_filename(item, "audio"))
    if spoken.get("ok") and spoken.get("text"):
        result.transcript = str(spoken["text"]).strip()
        text_parts.append(result.transcript)
        return
    result.fetch_errors.append(str(spoken.get("error") or "stt_failed"))
    text_parts.append(_PIPELINE_LABELS["audio"])


async def _ingest_video(
    *,
    tenant_id: str,
    item: dict[str, Any],
    blob: bytes,
    mime: str,
    video_fn: VideoFn,
    stt: TranscribeFn,
    result: InboundMediaResult,
    text_parts: list[str],
) -> None:
    _ = mime
    if not blob:
        result.video_status = "video_bytes_unavailable"
        text_parts.append(_PIPELINE_LABELS["video"])
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
        spoken = await stt(data=audio, filename="video_audio.wav")
        if spoken.get("ok") and spoken.get("text"):
            result.transcript = str(spoken["text"]).strip()
            text_parts.append(result.transcript)
            return
        result.fetch_errors.append(str(spoken.get("error") or "video_stt_failed"))
    text_parts.append(_PIPELINE_LABELS["video"])
    if result.video_status in {"ffmpeg_unavailable", "video_extract_failed", "empty_video", "video_too_large"}:
        result.fetch_errors.append(result.video_status)


def _ingest_file(
    *,
    item: dict[str, Any],
    blob: bytes,
    mime: str,
    result: InboundMediaResult,
    text_parts: list[str],
) -> None:
    if not blob:
        text_parts.append(_PIPELINE_LABELS["file"])
        return
    extracted = extract_inbound_file(data=blob, mime=mime, filename=_filename(item, "file"))
    result.extract = str(extracted.get("text") or "")
    if result.extract:
        text_parts.append(result.extract[:2000])
        return
    result.fetch_errors.append(str(extracted.get("status") or "file_extract_empty"))
    text_parts.append(_PIPELINE_LABELS["file"])
