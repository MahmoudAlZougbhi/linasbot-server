"""Tenant-scoped product image storage (object storage on disk, not DB blobs)."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import time
import uuid
from pathlib import Path
from typing import Any

from services.products.paths import product_media_dir

MEDIA_ID_PREFIX = "prdim_"
ALLOWED_MIME = frozenset(
    {
        "image/jpeg",
        "image/png",
        "image/heic",
        "image/heif",
        "image/webp",
    }
)
MAX_BYTES = 8 * 1024 * 1024  # 8 MiB per product image


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
        }
        if ext in ext_map and mime in {"", "application/octet-stream"}:
            mime = ext_map[ext]
        else:
            return {"ok": False, "error": "unsupported_mime", "mime": mime}
    return {"ok": True, "mime": mime}


def store_product_media(
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
    media_id = f"{MEDIA_ID_PREFIX}{uuid.uuid4().hex}"
    mime = str(check["mime"])
    meta = {
        "media_id": media_id,
        "tenant_id": tenant_id,
        "user_id": user_id,
        "filename": Path(filename).name[:180],
        "mime": mime,
        "size": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "created_at": time.time(),
    }
    base = product_media_dir(tenant_id)
    base.mkdir(parents=True, exist_ok=True)
    (base / f"{media_id}.bin").write_bytes(content)
    (base / f"{media_id}.json").write_text(json.dumps(meta), encoding="utf-8")
    return {"ok": True, **meta}


def load_media_meta(*, tenant_id: str, media_id: str) -> dict[str, Any] | None:
    safe = (media_id or "").strip()
    if not safe.startswith(MEDIA_ID_PREFIX):
        return None
    path = product_media_dir(tenant_id) / f"{safe}.json"
    if not path.is_file():
        return None
    try:
        meta = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(meta, dict):
        return None
    if str(meta.get("tenant_id") or "") != tenant_id:
        return None
    return meta


def load_media_bytes(*, tenant_id: str, media_id: str) -> bytes | None:
    meta = load_media_meta(tenant_id=tenant_id, media_id=media_id)
    if not meta:
        return None
    path = product_media_dir(tenant_id) / f"{media_id}.bin"
    if not path.is_file():
        return None
    try:
        return path.read_bytes()
    except OSError:
        return None


def delete_product_media(*, tenant_id: str, media_id: str) -> None:
    safe = (media_id or "").strip()
    if not safe.startswith(MEDIA_ID_PREFIX):
        return
    base = product_media_dir(tenant_id)
    for suffix in (".bin", ".json"):
        path = base / f"{safe}{suffix}"
        if path.is_file():
            path.unlink(missing_ok=True)
