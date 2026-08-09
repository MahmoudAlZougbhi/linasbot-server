"""Tenant-scoped owner attachments (private, validated MIME/size)."""

from __future__ import annotations

import hashlib
import mimetypes
import time
import uuid
from pathlib import Path
from typing import Any

from storage.persistent_storage import _DATA_ROOT

ALLOWED_MIME = frozenset(
    {
        "image/jpeg",
        "image/png",
        "image/heic",
        "image/heif",
        "application/pdf",
    }
)
MAX_BYTES = 12 * 1024 * 1024  # 12 MiB


def _root() -> Path:
    p = Path(_DATA_ROOT) / "owner_attachments"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _tenant_dir(tenant_id: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in tenant_id)[:80]
    d = _root() / safe
    d.mkdir(parents=True, exist_ok=True)
    return d


def validate_upload(*, filename: str, content_type: str | None, size: int) -> dict[str, Any]:
    mime = (content_type or mimetypes.guess_type(filename)[0] or "").lower()
    if size <= 0:
        return {"ok": False, "error": "empty_file"}
    if size > MAX_BYTES:
        return {"ok": False, "error": "file_too_large", "max_bytes": MAX_BYTES}
    if mime not in ALLOWED_MIME:
        # HEIC sometimes arrives as application/octet-stream — allow by extension
        ext = Path(filename).suffix.lower()
        if ext in {".heic", ".heif"} and mime in {"", "application/octet-stream"}:
            mime = "image/heic"
        elif ext in {".jpg", ".jpeg"} and mime in {"", "application/octet-stream"}:
            mime = "image/jpeg"
        elif ext == ".png" and mime in {"", "application/octet-stream"}:
            mime = "image/png"
        elif ext == ".pdf" and mime in {"", "application/octet-stream"}:
            mime = "application/pdf"
        else:
            return {"ok": False, "error": "unsupported_mime", "mime": mime}
    return {"ok": True, "mime": mime}


def store_attachment(
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
    attachment_id = f"att_{uuid.uuid4().hex}"
    digest = hashlib.sha256(content).hexdigest()
    meta = {
        "attachment_id": attachment_id,
        "tenant_id": tenant_id,
        "user_id": user_id,
        "filename": Path(filename).name[:180],
        "mime": check["mime"],
        "size": len(content),
        "sha256": digest,
        "created_at": time.time(),
        "public_url": None,  # never permanent public URL
    }
    base = _tenant_dir(tenant_id)
    (base / f"{attachment_id}.bin").write_bytes(content)
    import json

    (base / f"{attachment_id}.json").write_text(json.dumps(meta), encoding="utf-8")
    return {"ok": True, **meta}


def load_attachment_meta(*, tenant_id: str, attachment_id: str) -> dict[str, Any] | None:
    import json

    path = _tenant_dir(tenant_id) / f"{attachment_id}.json"
    if not path.exists():
        return None
    meta = json.loads(path.read_text(encoding="utf-8"))
    if str(meta.get("tenant_id")) != tenant_id:
        return None
    return meta


def load_attachment_bytes(*, tenant_id: str, attachment_id: str) -> bytes | None:
    meta = load_attachment_meta(tenant_id=tenant_id, attachment_id=attachment_id)
    if not meta:
        return None
    path = _tenant_dir(tenant_id) / f"{attachment_id}.bin"
    if not path.exists():
        return None
    return path.read_bytes()


def supported_attachment_types() -> list[dict[str, str]]:
    return [
        {"mime": "image/jpeg", "ext": ".jpg"},
        {"mime": "image/png", "ext": ".png"},
        {"mime": "image/heic", "ext": ".heic"},
        {"mime": "image/heif", "ext": ".heif"},
        {"mime": "application/pdf", "ext": ".pdf"},
    ]
