# -*- coding: utf-8 -*-
"""
Shared media helpers for dashboard playback and WhatsApp delivery.
"""

import mimetypes
import os
from pathlib import Path
from typing import Optional
from urllib.parse import quote, unquote, urlparse


PROJECT_ROOT = Path(__file__).resolve().parent.parent
MEDIA_SERVE_DIR = PROJECT_ROOT / "static" / "audio"
MEDIA_SERVE_DIR.mkdir(parents=True, exist_ok=True)


_CONTENT_TYPE_OVERRIDES = {
    ".ogg": "audio/ogg",
    ".opus": "audio/ogg",
    ".webm": "audio/webm",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
}


def get_public_base_url() -> str:
    """
    Resolve the public base URL for externally reachable media links.
    """
    configured_url = os.getenv("BOT_PUBLIC_URL", "").strip()
    configured_domain = os.getenv("BOT_PUBLIC_DOMAIN", "").strip()

    value = configured_url or configured_domain
    if not value:
        return "https://linasaibot.com"

    if value.startswith(("http://", "https://")):
        return value.rstrip("/")

    return f"https://{value.strip('/')}"


def sanitize_media_filename(filename: str) -> str:
    """
    Return a safe basename for local media access.
    """
    decoded = unquote((filename or "").strip())
    if not decoded:
        return ""

    safe_name = os.path.basename(decoded)
    if safe_name in {"", ".", ".."}:
        return ""

    return safe_name


def resolve_media_file_path(filename: str) -> Optional[Path]:
    """
    Resolve a requested media filename into a safe absolute path.
    """
    safe_name = sanitize_media_filename(filename)
    if not safe_name:
        return None

    candidate_path = (MEDIA_SERVE_DIR / safe_name).resolve()
    media_root = MEDIA_SERVE_DIR.resolve()

    try:
        candidate_path.relative_to(media_root)
    except ValueError:
        return None

    return candidate_path


def get_media_content_type(filename: str) -> str:
    """
    Resolve content type for media playback.
    """
    safe_name = sanitize_media_filename(filename)
    if not safe_name:
        return "application/octet-stream"

    ext = Path(safe_name).suffix.lower()
    if ext in _CONTENT_TYPE_OVERRIDES:
        return _CONTENT_TYPE_OVERRIDES[ext]

    guessed_type, _ = mimetypes.guess_type(safe_name)
    return guessed_type or "application/octet-stream"


def build_public_media_url(filename: str) -> str:
    """
    Build a media serve URL from filename.
    """
    safe_name = sanitize_media_filename(filename)
    if not safe_name:
        return ""

    encoded_name = quote(safe_name)
    base_url = get_public_base_url()
    if base_url:
        return f"{base_url}/api/media/serve/{encoded_name}"

    return f"/api/media/serve/{encoded_name}"


def extract_media_filename_from_url(media_url: str) -> str:
    """
    Extract a local filename from known media URL formats.
    """
    if not media_url:
        return ""

    parsed = urlparse(media_url)

    if parsed.scheme in {"http", "https"}:
        path = parsed.path or ""

        if "/api/media/serve/" in path:
            path_after_serve = path.split("/api/media/serve/", 1)[1]
            return sanitize_media_filename(path_after_serve)

        if "/o/" in path:
            # Firebase URL path: /v0/b/<bucket>/o/<encoded-filename>
            encoded_storage_path = path.split("/o/", 1)[1]
            decoded_storage_path = unquote(encoded_storage_path)
            return sanitize_media_filename(decoded_storage_path)

        return sanitize_media_filename(path)

    if "/api/media/serve/" in media_url:
        path_after_serve = media_url.split("/api/media/serve/", 1)[1]
        return sanitize_media_filename(path_after_serve)

    return sanitize_media_filename(media_url)


def build_whatsapp_audio_delivery_url(storage_url: str) -> str:
    """
    Build the most reliable WhatsApp-deliverable URL for stored audio.
    """
    if not storage_url:
        return ""

    parsed = urlparse(storage_url)

    # Already an absolute media-serve URL.
    if parsed.scheme in {"http", "https"} and "/api/media/serve/" in parsed.path:
        return storage_url

    # Relative local media path.
    if storage_url.startswith("/api/media/serve/"):
        base_url = get_public_base_url()
        if base_url:
            return f"{base_url}{storage_url}"
        return storage_url

    filename = extract_media_filename_from_url(storage_url)
    if not filename:
        return storage_url

    media_url = build_public_media_url(filename)

    # If no public domain is configured, keep externally reachable source URL.
    if media_url.startswith("/") and parsed.scheme in {"http", "https"}:
        return storage_url

    return media_url
