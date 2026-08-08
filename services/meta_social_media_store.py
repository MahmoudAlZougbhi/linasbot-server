"""Temporary media storage for Meta social post publishing (tenant-isolated)."""

from __future__ import annotations

import hashlib
import hmac
import mimetypes
import os
import secrets
import time
import uuid
from pathlib import Path

from storage.persistent_storage import _DATA_ROOT

_MEDIA_ROOT = Path(_DATA_ROOT) / "meta_social_post_media"
_MEDIA_TTL_SECONDS = 3600
_ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png"}
_ALLOWED_MIME = {"image/jpeg", "image/png"}


def _signing_secret() -> bytes:
    secret = (
        os.getenv("META_APP_A_SECRET")
        or os.getenv("META_APP_SECRET")
        or os.getenv("DASHBOARD_SESSION_SECRET")
        or ""
    ).strip()
    if not secret:
        raise RuntimeError("Meta social media signing secret is not configured")
    return secret.encode("utf-8")


def _tenant_dir(tenant_id: str) -> Path:
    safe = hashlib.sha256(tenant_id.encode("utf-8")).hexdigest()[:32]
    return _MEDIA_ROOT / safe


def _purge_stale_files(directory: Path) -> None:
    cutoff = time.time() - _MEDIA_TTL_SECONDS
    if not directory.exists():
        return
    for path in directory.iterdir():
        if not path.is_file():
            continue
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink(missing_ok=True)
        except OSError:
            continue


def save_uploaded_media(*, tenant_id: str, filename: str, content: bytes, content_type: str) -> str:
    """Persist an uploaded image and return an opaque media_id."""

    ext = Path(filename or "").suffix.lower()
    if ext not in _ALLOWED_EXTENSIONS:
        ext = ".jpg" if content_type == "image/jpeg" else ".png" if content_type == "image/png" else ""
    if ext not in _ALLOWED_EXTENSIONS:
        raise ValueError("Only JPEG and PNG images are supported")
    if content_type not in _ALLOWED_MIME:
        raise ValueError("Unsupported media content type")
    if len(content) > 8 * 1024 * 1024:
        raise ValueError("Image exceeds 8 MB limit")

    directory = _tenant_dir(tenant_id)
    directory.mkdir(parents=True, exist_ok=True)
    _purge_stale_files(directory)
    media_id = uuid.uuid4().hex
    path = directory / f"{media_id}{ext}"
    path.write_bytes(content)
    return media_id


def resolve_media_path(*, tenant_id: str, media_id: str) -> Path | None:
    directory = _tenant_dir(tenant_id)
    if not directory.exists():
        return None
    for ext in _ALLOWED_EXTENSIONS:
        candidate = directory / f"{media_id}{ext}"
        if candidate.exists():
            if time.time() - candidate.stat().st_mtime > _MEDIA_TTL_SECONDS:
                candidate.unlink(missing_ok=True)
                return None
            return candidate
    return None


def media_content_type(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(str(path))
    return guessed if guessed in _ALLOWED_MIME else "image/jpeg"


def build_media_access_token(*, tenant_id: str, media_id: str, expires_at: int) -> str:
    payload = f"{tenant_id}:{media_id}:{expires_at}"
    digest = hmac.new(_signing_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{expires_at}.{digest}"


def verify_media_access_token(*, tenant_id: str, media_id: str, token: str) -> bool:
    parts = token.split(".", 1)
    if len(parts) != 2:
        return False
    try:
        expires_at = int(parts[0])
    except ValueError:
        return False
    if expires_at < int(time.time()):
        return False
    expected = build_media_access_token(tenant_id=tenant_id, media_id=media_id, expires_at=expires_at)
    return hmac.compare_digest(token, expected)


def tenant_media_hash(tenant_id: str) -> str:
    return hashlib.sha256(tenant_id.encode("utf-8")).hexdigest()[:16]


def public_media_url(*, base_url: str, tenant_id: str, media_id: str) -> str:
    expires_at = int(time.time()) + _MEDIA_TTL_SECONDS
    token = build_media_access_token(tenant_id=tenant_id, media_id=media_id, expires_at=expires_at)
    tenant_hash = tenant_media_hash(tenant_id)
    base = base_url.rstrip("/")
    return f"{base}/api/meta/social-posts/media/{tenant_hash}/{media_id}?token={token}"
