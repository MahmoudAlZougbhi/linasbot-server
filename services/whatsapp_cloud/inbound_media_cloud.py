"""Store Cloud inbound image/audio/video/file for Brain. Fail soft; never invent transcripts."""

from __future__ import annotations

from typing import Any


def _load_token(snapshot: dict[str, Any]) -> str:
    connection_id = str(snapshot.get("connection_id") or "").strip()
    if not connection_id:
        return ""
    try:
        from db.session import whatsapp_session
        from services.whatsapp_cloud.repository import WhatsAppCloudRepository

        with whatsapp_session() as session:
            repo = WhatsAppCloudRepository(session)
            conn = repo.get_connection(connection_id)
            if conn is None:
                return ""
            return str(repo.load_access_token(conn) or "")
    except Exception:
        return ""


async def _download(snapshot: dict[str, Any], token: str) -> tuple[bytes, str] | None:
    media_id = str(snapshot.get("media_id") or "").strip()
    if not media_id or not token:
        return None
    try:
        from services.whatsapp_cloud.graph_client import download_media_bytes

        return await download_media_bytes(access_token=token, media_id=media_id)
    except Exception:
        return None


def _store_image(snapshot: dict[str, Any], content: bytes, mime: str) -> None:
    from services.customer_reply_v2.inbound_media import store_inbound_image

    stored = store_inbound_image(
        {"tenant_id": str(snapshot.get("tenant_id") or "")},
        content=content,
        filename="whatsapp.jpg",
        content_type=mime or "image/jpeg",
    )
    if stored:
        snapshot["image_media_id"] = stored


def _filename(mime: str) -> str:
    kind = (mime or "").lower()
    if "pdf" in kind:
        return "inbound.pdf"
    if "word" in kind or "docx" in kind:
        return "inbound.docx"
    if kind.startswith("text/") or kind.endswith("/json"):
        return "inbound.txt"
    return "inbound.bin"


def _ingest_document(snapshot: dict[str, Any], content: bytes, mime: str) -> None:
    from services.customer_reply_v2.inbound_extract import extract_inbound_file

    extracted = extract_inbound_file(data=content, mime=mime or "", filename=_filename(mime))
    text = str(extracted.get("text") or "").strip()
    if text:
        snapshot["extract"] = text[:2000]


async def _ingest_video(snapshot: dict[str, Any], content: bytes) -> None:
    from services.customer_reply_v2.inbound_video import extract_bounded_video

    extracted = extract_bounded_video(content)
    snapshot["video_status"] = str(extracted.get("status") or "")
    frames = list(extracted.get("frames") or [])
    if frames:
        _store_image(snapshot, frames[0], "image/jpeg")
    audio = extracted.get("audio")
    if audio:
        await _transcribe_audio(snapshot, audio)


async def _transcribe_audio(snapshot: dict[str, Any], content: bytes) -> None:
    from services.customer_reply_v2.inbound_stt import transcribe_inbound_audio
    from services.membership.provider_expense import record_pending_provider

    spoken = await transcribe_inbound_audio(data=content, filename="voice.ogg")
    tenant_id = str(snapshot.get("tenant_id") or "")
    if tenant_id:
        record_pending_provider(
            event_id=f"stt:{tenant_id}:{snapshot.get('media_id') or 'voice'}",
            tenant_id=tenant_id,
            category="stt",
            feature="inbound_media",
            provider="openai",
            model=str(spoken.get("model") or "stt"),
            operation_id=str(snapshot.get("provider_message_id") or snapshot.get("media_id") or ""),
        )
    text = str(spoken.get("text") or "").strip() if spoken.get("ok") else ""
    if text:
        snapshot["transcript"] = text


async def hydrate_cloud_inbound_snapshot(snapshot: dict[str, Any] | None) -> dict[str, Any] | None:
    """Download Graph media once and stamp resource id / transcript before generate."""
    if not snapshot:
        return snapshot
    kind = str(snapshot.get("message_type") or "").lower()
    if kind not in {"image", "audio", "video", "document"}:
        return snapshot
    if kind == "image" and str(snapshot.get("image_media_id") or "").startswith("prdim_"):
        return snapshot
    if kind == "audio" and str(snapshot.get("transcript") or "").strip():
        return snapshot
    if kind == "video" and (
        str(snapshot.get("image_media_id") or "").startswith("prdim_")
        or str(snapshot.get("transcript") or "").strip()
        or snapshot.get("video_status")
    ):
        return snapshot
    if kind == "document" and str(snapshot.get("extract") or "").strip():
        return snapshot
    token = _load_token(snapshot)
    downloaded = await _download(snapshot, token)
    if not downloaded:
        return snapshot
    content, mime = downloaded
    mime = str(snapshot.get("media_mime") or mime or "")
    if kind == "image":
        _store_image(snapshot, content, mime)
    elif kind == "audio":
        await _transcribe_audio(snapshot, content)
    elif kind == "video":
        await _ingest_video(snapshot, content)
    else:
        _ingest_document(snapshot, content, mime)
    return snapshot
