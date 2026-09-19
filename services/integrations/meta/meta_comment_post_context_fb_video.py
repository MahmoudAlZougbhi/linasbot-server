"""Extract a playable Facebook video URL from Graph post payloads."""

from __future__ import annotations

from typing import Any

FB_POST_FIELDS = (
    "message,story,full_picture,type,source,status_type,"
    "attachments{media_type,type,url,unshimmed_url,media,target,"
    "subattachments{media_type,type,url,unshimmed_url,media,target}}"
)
FB_COMMENT_FIELDS = (
    "post{id,message,story,full_picture,type,source,"
    "attachments{media_type,type,url,unshimmed_url,media,target}},"
    "parent{id,message,from},from,message,id"
)
FB_VIDEO_OBJECT_FIELDS = "source,length,picture"

_PERMALINK_MARKERS = ("instagram.com/", "facebook.com/", "fb.com/", "fb.watch")


def is_site_permalink(url: str) -> bool:
    lowered = (url or "").strip().lower()
    return any(token in lowered for token in _PERMALINK_MARKERS)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def playable_https(url: str) -> str:
    value = (url or "").strip()
    if not value or is_site_permalink(value):
        return ""
    lowered = value.lower()
    if lowered.startswith("http://") or lowered.startswith("https://"):
        return value
    return ""


def _looks_like_image_url(url: str) -> bool:
    path = (url or "").lower().split("?", 1)[0]
    return path.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"))


def attachment_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    attachments = _as_dict(payload.get("attachments"))
    raw = attachments.get("data")
    rows = raw if isinstance(raw, list) else []
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        out.append(row)
        nested_raw = _as_dict(row.get("subattachments")).get("data")
        nested = nested_raw if isinstance(nested_raw, list) else []
        for item in nested:
            if isinstance(item, dict):
                out.append(item)
    return out


def facebook_looks_like_video(payload: dict[str, Any]) -> bool:
    label = str(payload.get("media_type") or payload.get("type") or payload.get("status_type") or "").upper()
    if label in {"IMAGE", "PHOTO", "CAROUSEL_ALBUM"}:
        return False
    if label in {"VIDEO", "REEL", "STORY"} or "VIDEO" in label or "REEL" in label:
        return True
    for row in attachment_rows(payload):
        kind = str(row.get("media_type") or row.get("type") or "").upper()
        if "VIDEO" in kind or "REEL" in kind:
            return True
    return bool(facebook_playable_video_url(payload))


def facebook_playable_video_url(payload: dict[str, Any]) -> str:
    label = str(payload.get("media_type") or payload.get("type") or "").upper()
    if label in {"IMAGE", "PHOTO", "CAROUSEL_ALBUM"}:
        return ""
    for key in ("source", "media_url"):
        found = playable_https(str(payload.get(key) or ""))
        if found and not _looks_like_image_url(found):
            return found
    media = _as_dict(payload.get("media"))
    found = playable_https(str(media.get("source") or media.get("src") or ""))
    if found and not _looks_like_image_url(found):
        return found
    for row in attachment_rows(payload):
        media = _as_dict(row.get("media"))
        found = playable_https(str(media.get("source") or media.get("src") or row.get("unshimmed_url") or ""))
        if found and not _looks_like_image_url(found):
            return found
    return ""


def facebook_cover_urls(payload: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    for key in ("full_picture", "picture", "thumbnail_url"):
        found = playable_https(str(payload.get(key) or ""))
        if found and found not in urls:
            urls.append(found)
    media = _as_dict(payload.get("media"))
    image = _as_dict(media.get("image"))
    found = playable_https(str(image.get("src") or image.get("url") or ""))
    if found and found not in urls:
        urls.append(found)
    for row in attachment_rows(payload):
        media = _as_dict(row.get("media"))
        image = _as_dict(media.get("image"))
        found = playable_https(str(image.get("src") or image.get("url") or ""))
        if found and found not in urls:
            urls.append(found)
    return urls


def facebook_video_target_id(payload: dict[str, Any]) -> str:
    for row in attachment_rows(payload):
        target = _as_dict(row.get("target"))
        vid = str(target.get("id") or "").strip()
        if vid:
            return vid
    return str(payload.get("object_id") or "").strip()


def facebook_media_type_label(payload: dict[str, Any]) -> str:
    if facebook_looks_like_video(payload):
        return "VIDEO"
    return str(payload.get("media_type") or payload.get("type") or "").strip()
