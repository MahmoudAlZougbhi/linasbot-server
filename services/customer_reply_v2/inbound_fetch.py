"""SSRF-safe download of customer inbound attachment URLs."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx

from services.ssrf_guard import SSRFValidationError, validate_fetch_url

MAX_REDIRECTS = 3
FETCH_TIMEOUT_S = 12.0
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_AUDIO_BYTES = 15 * 1024 * 1024
MAX_VIDEO_BYTES = 12 * 1024 * 1024


def max_bytes_for_kind(kind: str) -> int:
    if kind == "video":
        return MAX_VIDEO_BYTES
    if kind == "audio":
        return MAX_AUDIO_BYTES
    if kind == "image":
        return MAX_IMAGE_BYTES
    return MAX_FILE_BYTES


async def fetch_inbound_url(url: str, *, max_bytes: int) -> dict[str, Any]:
    try:
        current = validate_fetch_url(url, allowed_schemes=("https",))
    except SSRFValidationError as exc:
        return {"ok": False, "error": f"ssrf_blocked:{exc}", "bytes": b"", "mime": "", "url": ""}
    timeout = httpx.Timeout(FETCH_TIMEOUT_S)
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            for _ in range(MAX_REDIRECTS + 1):
                response = await client.get(current)
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location") or ""
                    if not location:
                        return {"ok": False, "error": "redirect_missing_location", "bytes": b"", "mime": "", "url": ""}
                    if location.startswith("/"):
                        from urllib.parse import urljoin

                        location = urljoin(current, location)
                    current = validate_fetch_url(location, allowed_schemes=("https",))
                    continue
                if response.status_code != 200:
                    return {
                        "ok": False,
                        "error": f"http_{response.status_code}",
                        "bytes": b"",
                        "mime": "",
                        "url": current,
                    }
                raw = response.content or b""
                if len(raw) > max_bytes:
                    return {"ok": False, "error": "payload_too_large", "bytes": b"", "mime": "", "url": current}
                mime = str(response.headers.get("content-type") or "").split(";")[0].strip().lower()
                return {"ok": True, "error": "", "bytes": raw, "mime": mime, "url": current}
    except SSRFValidationError as exc:
        return {"ok": False, "error": f"ssrf_blocked:{exc}", "bytes": b"", "mime": "", "url": ""}
    except Exception as exc:
        return {"ok": False, "error": f"fetch_failed:{type(exc).__name__}", "bytes": b"", "mime": "", "url": ""}
    return {"ok": False, "error": "too_many_redirects", "bytes": b"", "mime": "", "url": ""}


def link_host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""
