"""Comment media context: image/carousel/video cached summaries (no creative generation)."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from services.customer_reply_v2.flags import customer_media_context_enabled
from services.customer_reply_v2.models import CommentMediaContext
from storage.persistent_storage import get_data_root

MAX_CAROUSEL_THUMBS = 3
MAX_VIDEO_FRAMES = 3


def _cache_path(tenant_id: str, media_revision: str) -> Path:
    root = Path(get_data_root()) / "tenants" / tenant_id / "customer_reply_v2" / "media_cache"
    root.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(media_revision.encode()).hexdigest()[:40]
    return root / f"{key}.json"


def load_cached_media(tenant_id: str, media_revision: str) -> dict[str, Any] | None:
    path = _cache_path(tenant_id, media_revision)
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return raw if isinstance(raw, dict) else None


def save_cached_media(tenant_id: str, media_revision: str, payload: dict[str, Any]) -> None:
    path = _cache_path(tenant_id, media_revision)
    payload = {**payload, "cached_at": time.time(), "media_revision": media_revision}
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _visual_reference(comment_text: str) -> bool:
    import re

    return bool(
        re.search(
            r"\b(this|that\s+one|the\s+one|color|shown|in\s+the\s+(video|photo|image)|"
            r"هيدا|هيدي|الصورة|بالفيديو|هاد)\b",
            comment_text or "",
            re.I,
        )
    )


def build_comment_media_context(
    *,
    tenant_id: str,
    comment_text: str,
    caption: str = "",
    media_type: str = "",
    parent_comment: str = "",
    nearby_replies: list[str] | None = None,
    image_urls: list[str] | None = None,
    media_id: str = "",
    media_revision: str = "",
    injected_cache: dict[str, Any] | None = None,
) -> CommentMediaContext:
    """Assemble bounded comment/post context. Never downloads unbounded media collections."""
    if not customer_media_context_enabled() and injected_cache is None:
        return CommentMediaContext(
            media_type=media_type or "unknown",
            caption=caption or "",
            parent_comment=parent_comment or "",
            nearby_replies=list(nearby_replies or [])[:5],
            uncertainty_required=False,
        )

    revision = media_revision or media_id or hashlib.sha256((caption + media_type).encode()).hexdigest()[:24]
    cached = injected_cache if injected_cache is not None else load_cached_media(tenant_id, revision)
    mtype = (media_type or (cached or {}).get("media_type") or "unknown").lower()

    urls = list(image_urls or [])[:MAX_CAROUSEL_THUMBS]
    summary = str((cached or {}).get("visual_summary") or "")
    frames = int((cached or {}).get("frame_count") or 0)
    uncertainty = False

    if mtype in {"video", "reel"}:
        # Never send raw video. Use caption + cached summary/frames.
        if _visual_reference(comment_text) and frames <= 0 and not summary:
            uncertainty = True
        urls = list((cached or {}).get("frame_urls") or urls)[:MAX_VIDEO_FRAMES]
    elif mtype == "carousel":
        urls = urls[:MAX_CAROUSEL_THUMBS]
    elif mtype == "image":
        urls = urls[:1]

    if not caption and not summary and not urls:
        uncertainty = True

    return CommentMediaContext(
        media_type=mtype,
        caption=caption or str((cached or {}).get("caption") or ""),
        parent_comment=parent_comment or "",
        nearby_replies=list(nearby_replies or [])[:5],
        image_urls=urls,
        cached_visual_summary=summary,
        frame_count=frames,
        uncertainty_required=uncertainty,
        media_revision=revision,
    )


def seed_video_cache_for_tests(
    *,
    tenant_id: str,
    media_revision: str,
    caption: str,
    visual_summary: str,
    frame_urls: list[str] | None = None,
) -> None:
    """Fixture helper: cache video/reel context without live Meta mutation."""
    save_cached_media(
        tenant_id,
        media_revision,
        {
            "media_type": "video",
            "caption": caption,
            "visual_summary": visual_summary,
            "frame_urls": list(frame_urls or [])[:MAX_VIDEO_FRAMES],
            "frame_count": min(len(frame_urls or []), MAX_VIDEO_FRAMES) or (3 if visual_summary else 0),
        },
    )


def media_context_to_dict(ctx: CommentMediaContext) -> dict[str, Any]:
    return {
        "media_type": ctx.media_type,
        "caption": ctx.caption,
        "parent_comment": ctx.parent_comment,
        "nearby_replies": ctx.nearby_replies,
        "image_url_count": len(ctx.image_urls),
        "cached_visual_summary": ctx.cached_visual_summary,
        "frame_count": ctx.frame_count,
        "uncertainty_required": ctx.uncertainty_required,
        "media_revision": ctx.media_revision,
        # Do not dump full URLs into traces by default — count only in observability.
    }
