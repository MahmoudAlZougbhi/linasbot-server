"""Tenant-scoped CM article media (images/files for case examples).

Binaries stay under ``{DATA_ROOT}/tenants/{tenant}/cm/media/``; article JSON only
stores metadata + captions. No public permanent URLs.
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import time
import uuid
from pathlib import Path
from typing import Any

from services.cm.paths import media_dir

ALLOWED_MIME = frozenset(
    {
        "image/jpeg",
        "image/png",
        "image/heic",
        "image/heif",
        "image/webp",
        "video/mp4",
        "video/quicktime",
        "video/webm",
        "video/3gpp",
        "application/pdf",
        "text/plain",
        "text/markdown",
        "application/json",
    }
)
MAX_BYTES = 12 * 1024 * 1024  # 12 MiB
MAX_TEXT_EXCERPT = 2000
IMAGE_MIME_PREFIX = "image/"
VIDEO_MIME_PREFIX = "video/"


def _kind_for_mime(mime: str) -> str:
    lowered = (mime or "").lower()
    if lowered.startswith(IMAGE_MIME_PREFIX):
        return "image"
    if lowered.startswith(VIDEO_MIME_PREFIX):
        return "video"
    return "file"


def validate_upload(*, filename: str, content_type: str | None, size: int) -> dict[str, Any]:
    mime = (content_type or mimetypes.guess_type(filename)[0] or "").lower()
    if size <= 0:
        return {"ok": False, "error": "empty_file"}
    if size > MAX_BYTES:
        return {"ok": False, "error": "file_too_large", "max_bytes": MAX_BYTES}
    if mime not in ALLOWED_MIME:
        ext = Path(filename).suffix.lower()
        ext_map = {
            ".heic": "image/heic",
            ".heif": "image/heif",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
            ".mp4": "video/mp4",
            ".mov": "video/quicktime",
            ".webm": "video/webm",
            ".3gp": "video/3gpp",
            ".pdf": "application/pdf",
            ".txt": "text/plain",
            ".md": "text/markdown",
            ".json": "application/json",
        }
        if ext in ext_map and mime in {"", "application/octet-stream", "text/plain", "application/json"}:
            mime = ext_map[ext]
        else:
            return {"ok": False, "error": "unsupported_mime", "mime": mime}
    return {"ok": True, "mime": mime, "kind": _kind_for_mime(mime)}


def store_article_media(
    *,
    tenant_id: str,
    user_id: str,
    filename: str,
    content: bytes,
    content_type: str | None,
) -> dict[str, Any]:
    check = validate_upload(filename=filename, content_type=content_type, size=len(content))
    if not check.get("ok"):
        return check
    media_id = f"cmed_{uuid.uuid4().hex}"
    mime = str(check["mime"])
    meta = {
        "media_id": media_id,
        "tenant_id": tenant_id,
        "user_id": user_id,
        "filename": Path(filename).name[:180],
        "mime": mime,
        "kind": check["kind"],
        "size": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "created_at": time.time(),
    }
    base = media_dir(tenant_id)
    base.mkdir(parents=True, exist_ok=True)
    (base / f"{media_id}.bin").write_bytes(content)
    (base / f"{media_id}.json").write_text(json.dumps(meta), encoding="utf-8")
    return {"ok": True, **meta}


def load_media_meta(*, tenant_id: str, media_id: str) -> dict[str, Any] | None:
    safe = (media_id or "").strip()
    if not safe.startswith("cmed_") or "/" in safe or ".." in safe:
        return None
    path = media_dir(tenant_id) / f"{safe}.json"
    if not path.exists():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return None
    if str(raw.get("tenant_id") or "") != tenant_id:
        return None
    return raw


def load_media_bytes(*, tenant_id: str, media_id: str) -> bytes | None:
    meta = load_media_meta(tenant_id=tenant_id, media_id=media_id)
    if not meta:
        return None
    path = media_dir(tenant_id) / f"{media_id}.bin"
    if not path.exists():
        return None
    return path.read_bytes()


def text_excerpt_for_media(*, tenant_id: str, media_id: str, mime: str) -> str:
    """Include a short text excerpt for text-like attachments at index/prompt time."""
    if mime not in {"text/plain", "text/markdown", "application/json"}:
        return ""
    raw = load_media_bytes(tenant_id=tenant_id, media_id=media_id)
    if not raw:
        return ""
    try:
        text = raw.decode("utf-8", errors="replace").strip()
    except Exception:
        return ""
    if not text:
        return ""
    return text[:MAX_TEXT_EXCERPT]


def format_attachments_block(
    attachments: list[Any],
    *,
    tenant_id: str | None = None,
) -> str:
    """Human-readable case-example block for embed text / Owner read / prompts."""
    if not attachments:
        return ""
    lines: list[str] = ["CASE EXAMPLES (use when the caption matches the customer situation):"]
    for raw in attachments:
        if hasattr(raw, "model_dump"):
            att = raw.model_dump(mode="json")
        elif isinstance(raw, dict):
            att = raw
        else:
            continue
        kind = str(att.get("kind") or "file")
        filename = str(att.get("filename") or att.get("id") or "attachment")
        caption = str(att.get("caption") or "").strip() or "(no caption — describe when to use this)"
        mid = str(att.get("id") or "")
        mime = str(att.get("mime") or "")
        url = str(att.get("url") or "").strip()
        duration = att.get("duration_seconds")
        extra = ""
        if url:
            extra += f" url={url}"
        if isinstance(duration, int) and duration >= 0:
            extra += f" duration_seconds={duration}"
        line = f"- [{kind}] {filename}{extra}: {caption}"
        if tenant_id and mid and mime in {"text/plain", "text/markdown", "application/json"}:
            excerpt = text_excerpt_for_media(tenant_id=tenant_id, media_id=mid, mime=mime)
            if excerpt:
                line += f"\n  excerpt: {excerpt}"
        lines.append(line)
    return "\n".join(lines)
