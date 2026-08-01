# -*- coding: utf-8 -*-
"""
Media API module: Audio and media proxy endpoints
Handles proxying external audio URLs to avoid CORS issues in the browser.
"""

import httpx
from fastapi import Query, Request
from fastapi.responses import Response, FileResponse

from modules.core import app
from services.media_service import (
    resolve_media_file_path,
    get_media_content_type,
)
from services.ssrf_guard import SSRFValidationError, validate_fetch_url


MAX_AUDIO_BYTES = 15 * 1024 * 1024
MAX_REDIRECTS = 3


@app.api_route("/api/media/serve/{filename}", methods=["GET", "HEAD"])
async def serve_media_file(filename: str, request: Request):
    """Serve locally stored audio/media files for WhatsApp delivery"""
    file_path = resolve_media_file_path(filename)
    if not file_path or not file_path.exists():
        return Response(content="File not found", status_code=404)

    media_type = get_media_content_type(filename)
    file_size = file_path.stat().st_size

    if request.method == "HEAD":
        return Response(
            status_code=200,
            headers={
                "Content-Type": media_type,
                "Content-Length": str(file_size),
                "Accept-Ranges": "bytes",
            },
        )

    return FileResponse(str(file_path), media_type=media_type)


async def _fetch_with_ssrf_guard(url: str) -> httpx.Response:
    current = validate_fetch_url(url, allowed_schemes=("https",))
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=False) as client:
        for _ in range(MAX_REDIRECTS + 1):
            response = await client.get(current)
            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("location")
                if not location:
                    raise SSRFValidationError("Redirect without Location")
                # Absolute or relative
                if location.startswith("/"):
                    from urllib.parse import urlparse, urljoin

                    location = urljoin(current, location)
                current = validate_fetch_url(location, allowed_schemes=("https",))
                continue
            return response
    raise SSRFValidationError("Too many redirects")


@app.get("/api/media/audio")
async def proxy_audio(url: str = Query(..., description="The audio URL to proxy")):
    """
    Proxy audio from allowlisted external URLs to avoid CORS issues.
    """
    try:
        response = await _fetch_with_ssrf_guard(url)

        if response.status_code != 200:
            return Response(
                content="Failed to fetch audio",
                status_code=502,
                media_type="text/plain",
            )

        content = response.content
        if len(content) > MAX_AUDIO_BYTES:
            return Response(
                content="Audio too large",
                status_code=413,
                media_type="text/plain",
            )

        content_type = response.headers.get("content-type", "audio/ogg")
        if "audio" not in content_type.lower() and "octet-stream" not in content_type.lower():
            # Infer from URL extension when provider sends generic types
            lower = url.lower()
            if ".mp3" in lower:
                content_type = "audio/mpeg"
            elif ".wav" in lower:
                content_type = "audio/wav"
            elif ".ogg" in lower or ".opus" in lower:
                content_type = "audio/ogg"
            else:
                return Response(
                    content="Unsupported content type",
                    status_code=415,
                    media_type="text/plain",
                )

        return Response(
            content=content,
            media_type=content_type,
            headers={
                "Cache-Control": "private, max-age=3600",
                "X-Content-Type-Options": "nosniff",
            },
        )
    except SSRFValidationError as e:
        return Response(content=str(e) or "Invalid URL", status_code=400, media_type="text/plain")
    except Exception as e:
        print(f"Audio proxy error: {type(e).__name__}")
        return Response(content="Audio proxy failed", status_code=500, media_type="text/plain")
