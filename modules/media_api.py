# -*- coding: utf-8 -*-
"""
Media API module: Audio and media proxy endpoints
Handles proxying external audio URLs to avoid CORS issues in the browser.
"""

import os
import httpx
from urllib.parse import unquote
from fastapi import Query, Request
from fastapi.responses import Response, FileResponse

from modules.core import app

# Directory for locally served media files
MEDIA_SERVE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "audio")
os.makedirs(MEDIA_SERVE_DIR, exist_ok=True)


@app.api_route("/api/media/serve/{filename}", methods=["GET", "HEAD"])
async def serve_media_file(filename: str, request: Request):
    """Serve locally stored audio/media files for WhatsApp delivery"""
    file_path = os.path.join(MEDIA_SERVE_DIR, filename)
    if not os.path.exists(file_path):
        return Response(content="File not found", status_code=404)

    # Determine content type
    if filename.endswith(".ogg"):
        media_type = "audio/ogg"
    elif filename.endswith(".webm"):
        media_type = "audio/webm"
    elif filename.endswith(".mp3"):
        media_type = "audio/mpeg"
    else:
        media_type = "application/octet-stream"

    file_size = os.path.getsize(file_path)

    if request.method == "HEAD":
        return Response(
            status_code=200,
            headers={
                "Content-Type": media_type,
                "Content-Length": str(file_size),
                "Accept-Ranges": "bytes",
            }
        )

    return FileResponse(file_path, media_type=media_type)


@app.get("/api/media/audio")
async def proxy_audio(url: str = Query(..., description="The audio URL to proxy")):
    """
    Proxy audio from external URLs to avoid CORS issues.
    This endpoint fetches audio from WhatsApp/MontyMobile/Firebase and serves it
    with proper headers for browser playback.
    """
    try:
        # Use URL as-is (FastAPI already decodes query params once)
        decoded_url = url

        # Validate URL to prevent SSRF attacks
        if not decoded_url.startswith(('https://', 'http://')):
            return Response(
                content="Invalid URL",
                status_code=400,
                media_type="text/plain"
            )

        # Fetch the audio from the external URL
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(decoded_url)

            if response.status_code != 200:
                print(f"Failed to fetch audio from {decoded_url}: {response.status_code}")
                return Response(
                    content="Failed to fetch audio",
                    status_code=response.status_code,
                    media_type="text/plain"
                )

            # Determine content type from response or default to audio/ogg
            content_type = response.headers.get("content-type", "audio/ogg")

            # Common audio content types
            if "audio" not in content_type.lower():
                # Try to infer from URL
                if ".mp3" in decoded_url.lower():
                    content_type = "audio/mpeg"
                elif ".ogg" in decoded_url.lower():
                    content_type = "audio/ogg"
                elif ".opus" in decoded_url.lower():
                    content_type = "audio/opus"
                elif ".wav" in decoded_url.lower():
                    content_type = "audio/wav"
                elif ".m4a" in decoded_url.lower():
                    content_type = "audio/mp4"
                elif ".webm" in decoded_url.lower():
                    content_type = "audio/webm"
                else:
                    content_type = "audio/ogg"  # Default for WhatsApp voice messages

            # Return the audio with CORS-friendly headers
            return Response(
                content=response.content,
                status_code=200,
                media_type=content_type,
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, OPTIONS",
                    "Access-Control-Allow-Headers": "*",
                    "Cache-Control": "public, max-age=3600",  # Cache for 1 hour
                }
            )

    except httpx.TimeoutException:
        print(f"Timeout fetching audio from {url}")
        return Response(
            content="Request timeout",
            status_code=504,
            media_type="text/plain"
        )
    except Exception as e:
        print(f"Error proxying audio: {e}")
        return Response(
            content=f"Error: {str(e)}",
            status_code=500,
            media_type="text/plain"
        )
