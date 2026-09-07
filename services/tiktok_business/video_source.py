"""Resolve a TikTok post's caption, cover, and any official downloadable video URL."""

from __future__ import annotations

import json
from typing import Any

from services.tiktok_business.errors import TikTokApiError
from services.tiktok_business.http_client import tiktok_request

VIDEO_LIST_FIELDS = '["item_id","caption","thumbnail_url","share_url","embed_url","video_duration"]'
_SKIP_URL_KEYS = frozenset({"thumbnail_url", "cover_image_url", "poster_url", "share_url"})


def _as_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("videos", "list", "video_list"):
        rows = payload.get(key)
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return []


def _https(value: Any) -> str:
    text = str(value or "").strip()
    return text if text.startswith("https://") else ""


def _looks_like_video(url: str) -> bool:
    lowered = url.lower()
    path = lowered.split("?", 1)[0]
    if path.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif")):
        return False
    if path.endswith((".mp4", ".m3u8")):
        return True
    if "mime_type=video" in lowered or "contenttype=video" in lowered:
        return True
    return "/video/tos/" in path or "v16-" in path


def harvest_official_video_urls(payload: Any) -> list[str]:
    found: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            if str(key).lower() in _SKIP_URL_KEYS:
                continue
            if isinstance(value, str):
                url = _https(value)
                if url and _looks_like_video(url):
                    found.append(url)
            else:
                found.extend(harvest_official_video_urls(value))
    elif isinstance(payload, list):
        for item in payload:
            found.extend(harvest_official_video_urls(item))
    return found


def pick_tiktok_video_url(row: dict[str, Any] | None) -> str:
    urls = harvest_official_video_urls(row)
    return urls[0] if urls else ""


def parse_tiktok_video_item(row: dict[str, Any] | None) -> dict[str, str]:
    raw = row if isinstance(row, dict) else {}
    return {
        "item_id": str(raw.get("item_id") or raw.get("video_id") or raw.get("id") or "").strip(),
        "caption": str(raw.get("caption") or raw.get("video_description") or raw.get("title") or "").strip(),
        "thumbnail_url": _https(raw.get("thumbnail_url") or raw.get("cover_image_url") or raw.get("poster_url")),
        "share_url": _https(raw.get("share_url")),
        "video_url": pick_tiktok_video_url(raw),
    }


async def fetch_tiktok_video_item(
    *,
    access_token: str,
    open_id: str,
    video_id: str,
) -> dict[str, str]:
    """Load one owned video from Business video.list. Missing MP4 is returned honestly."""
    wanted = str(video_id or "").strip()
    if not wanted:
        return parse_tiktok_video_item({})
    params: dict[str, Any] = {
        "business_id": open_id,
        "fields": VIDEO_LIST_FIELDS,
        "max_count": 20,
        "filters": json.dumps({"video_ids": [wanted]}, separators=(",", ":")),
    }
    try:
        payload = await tiktok_request(
            method="GET",
            path="/business/video/list/",
            access_token=access_token,
            params=params,
        )
    except TikTokApiError:
        payload = {}
    match = next((row for row in _as_rows(payload) if parse_tiktok_video_item(row)["item_id"] == wanted), None)
    if match is None:
        try:
            fallback = await tiktok_request(
                method="GET",
                path="/business/video/list/",
                access_token=access_token,
                params={"business_id": open_id, "fields": VIDEO_LIST_FIELDS, "max_count": 20},
            )
        except TikTokApiError:
            fallback = {}
        match = next((row for row in _as_rows(fallback) if parse_tiktok_video_item(row)["item_id"] == wanted), None)
        payload = fallback or payload
    parsed = parse_tiktok_video_item(match)
    if not parsed["video_url"]:
        parsed["video_url"] = pick_tiktok_video_url(payload)
    return parsed
