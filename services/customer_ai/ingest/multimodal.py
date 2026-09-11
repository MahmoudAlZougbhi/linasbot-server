"""Async multimodal knowledge ingestion (PDF/image/audio/video) — not in turn latency."""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("customer_ai.ingest.multimodal")

SUPPORTED = frozenset({"text", "pdf", "image", "audio", "video"})


def classify_media(filename: str = "", content_type: str = "") -> str:
    name = (filename or "").lower()
    ctype = (content_type or "").lower()
    if ctype.startswith("text/") or name.endswith((".txt", ".md", ".markdown", ".json")):
        return "text"
    if "pdf" in ctype or name.endswith(".pdf"):
        return "pdf"
    if ctype.startswith("image/") or name.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
        return "image"
    if ctype.startswith("audio/") or name.endswith((".mp3", ".wav", ".m4a", ".ogg")):
        return "audio"
    if ctype.startswith("video/") or name.endswith((".mp4", ".mov", ".webm")):
        return "video"
    return "unsupported"


async def extract_pdf_text(data: bytes) -> dict[str, Any]:
    """Best-effort PDF text extraction. Fail visibly when library/backend missing."""
    if not data:
        return {"ok": False, "status": "FAILED", "reason": "empty_pdf", "text": "", "pages": 0}
    try:
        import io

        from pypdf import PdfReader  # type: ignore

        reader = PdfReader(io.BytesIO(data))
        pages: list[str] = []
        for page in reader.pages:
            pages.append((page.extract_text() or "").strip())
        text = "\n\n".join(p for p in pages if p)
        if not text.strip():
            return {"ok": False, "status": "FAILED", "reason": "pdf_no_text_layer", "text": "", "pages": len(pages)}
        return {"ok": True, "status": "READY", "reason": "ok", "text": text, "pages": len(pages), "headings_preserved": True}
    except Exception as exc:
        return {"ok": False, "status": "FAILED", "reason": f"pdf_extract_unavailable:{type(exc).__name__}", "text": "", "pages": 0}


async def extract_image_text(data: bytes, *, filename: str = "") -> dict[str, Any]:
    """OCR/vision representation for searchable index. Fail closed if provider missing."""
    if not data:
        return {"ok": False, "status": "FAILED", "reason": "empty_image", "text": ""}
    # Prefer existing inbound extract helpers when available; otherwise mark FAILED visibly.
    try:
        from services.customer_reply_v2.inbound_extract import extract_inbound_image  # type: ignore

        out = await extract_inbound_image(data, filename=filename)
        text = str((out or {}).get("text") or (out or {}).get("description") or "").strip()
        if not text:
            return {"ok": False, "status": "FAILED", "reason": "image_no_text", "text": ""}
        return {"ok": True, "status": "READY", "reason": "ok", "text": text, "source_ref": filename}
    except Exception as exc:
        return {
            "ok": False,
            "status": "FAILED",
            "reason": f"image_extract_unavailable:{type(exc).__name__}",
            "text": "",
            "source_ref": filename,
        }


async def extract_audio_transcript(data: bytes, *, filename: str = "") -> dict[str, Any]:
    if not data:
        return {"ok": False, "status": "FAILED", "reason": "empty_audio", "text": ""}
    try:
        from services.customer_reply_v2.inbound_extract import extract_inbound_audio  # type: ignore

        out = await extract_inbound_audio(data, filename=filename)
        text = str((out or {}).get("transcript") or (out or {}).get("text") or "").strip()
        if not text:
            return {"ok": False, "status": "FAILED", "reason": "audio_no_transcript", "text": ""}
        return {"ok": True, "status": "READY", "reason": "ok", "text": text, "source_ref": filename}
    except Exception as exc:
        return {
            "ok": False,
            "status": "FAILED",
            "reason": f"audio_extract_unavailable:{type(exc).__name__}",
            "text": "",
            "source_ref": filename,
        }


async def process_knowledge_media(
    *,
    tenant_id: str,
    filename: str,
    content_type: str,
    data: bytes,
) -> dict[str, Any]:
    """Async ingestion status machine: PROCESSING → INDEXING-ready text or FAILED."""
    kind = classify_media(filename, content_type)
    base = {
        "tenant_id": tenant_id,
        "filename": filename,
        "content_type": content_type,
        "media_kind": kind,
        "status": "PROCESSING",
    }
    if kind == "unsupported":
        return {**base, "ok": False, "status": "FAILED", "reason": "unsupported_media_type"}
    if kind == "text":
        text = data.decode("utf-8", errors="replace")
        return {**base, "ok": True, "status": "READY", "reason": "ok", "text": text}
    if kind == "pdf":
        result = await extract_pdf_text(data)
        return {**base, **result}
    if kind == "image":
        result = await extract_image_text(data, filename=filename)
        return {**base, **result}
    if kind == "audio":
        result = await extract_audio_transcript(data, filename=filename)
        return {**base, **result}
    if kind == "video":
        # Video: attempt audio transcript path only; keyframes optional/not fabricated.
        result = await extract_audio_transcript(data, filename=filename)
        if result.get("ok"):
            return {**base, **result, "media_kind": "video", "note": "transcript_only"}
        return {
            **base,
            "ok": False,
            "status": "FAILED",
            "reason": result.get("reason") or "video_transcript_unavailable",
            "text": "",
        }
    return {**base, "ok": False, "status": "FAILED", "reason": "unsupported_media_type"}
