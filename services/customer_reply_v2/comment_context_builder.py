"""Shared production Comment Context Builder for Instagram + Facebook comments.

Fetches post/media metadata via official Meta Graph APIs only, SSRF-safe media
download with size/time limits, and assembles bounded visual inputs for Answer Tera.
Never invents visuals; sets media_status honestly.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import tempfile
from pathlib import Path
from typing import Any

import httpx

from services.customer_reply_v2.inbound_video_comment import attach_comment_video_frames, ig_video_source
from services.customer_reply_v2.media_context import (
    MAX_CAROUSEL_THUMBS,
    MAX_VIDEO_FRAMES,
    build_comment_media_context,
    media_context_to_dict,
)
from services.customer_reply_v2.models import CommentMediaContext
from services.meta_app_registry import MetaAssetBinding
from services.meta_graph_routing import graph_api_url
from services.ssrf_guard import SSRFValidationError, validate_fetch_url

_logger = logging.getLogger("customer_reply_v2.comment_context")

MAX_MEDIA_BYTES = 4 * 1024 * 1024
FETCH_TIMEOUT_S = 12.0
# Bounded Graph thread fetch for comment context (same cap as history_format nearby replies).
MAX_THREAD_REPLIES = 8


def _author_from_graph_row(row: dict[str, Any]) -> tuple[str, str, bool]:
    from_raw = row.get("from")
    from_obj: dict[str, Any] = from_raw if isinstance(from_raw, dict) else {}
    author_id = str(from_obj.get("id") or row.get("from_id") or "").strip()
    author_name = str(
        from_obj.get("name") or from_obj.get("username") or row.get("username") or row.get("from_name") or ""
    ).strip()
    from_page = bool(row.get("is_hidden") is False and str(row.get("from_page") or "").strip())
    if str(row.get("from") or "") == "page":
        from_page = True
    return author_id, author_name, from_page


def _reply_record(row: dict[str, Any], *, text_key: str) -> dict[str, Any]:
    text = str(row.get(text_key) or row.get("message") or row.get("text") or "").strip()[:400]
    author_id, author_name, from_page = _author_from_graph_row(row)
    return {
        "text": text,
        "author_id": author_id,
        "author_name": author_name,
        "comment_id": str(row.get("id") or "").strip(),
        "from_page": from_page,
    }


def _normalize_media_type(raw: str) -> str:
    m = (raw or "").strip().upper()
    if m in {"IMAGE", "PHOTO"}:
        return "image"
    if m in {"VIDEO"}:
        return "video"
    if m in {"REELS", "REEL"}:
        return "reel"
    if m in {"CAROUSEL_ALBUM", "CAROUSEL", "ALBUM"}:
        return "carousel"
    if m in {"SHARE", "STATUS", "LINK"}:
        return "unknown"
    return (raw or "unknown").strip().lower() or "unknown"


def _collect_ig_urls(payload: dict[str, Any]) -> tuple[str, list[str], bool]:
    mtype = _normalize_media_type(str(payload.get("media_type") or ""))
    urls: list[str] = []
    truncated = False
    if mtype == "carousel":
        children = ((payload.get("children") or {}).get("data")) if isinstance(payload.get("children"), dict) else []
        if not isinstance(children, list):
            children = []
        for child in children:
            if not isinstance(child, dict):
                continue
            u = str(child.get("media_url") or child.get("thumbnail_url") or "").strip()
            if u:
                urls.append(u)
        if len(urls) > MAX_CAROUSEL_THUMBS:
            truncated = True
            urls = urls[:MAX_CAROUSEL_THUMBS]
    elif mtype in {"video", "reel"}:
        thumb = str(payload.get("thumbnail_url") or "").strip()
        if thumb:
            urls.append(thumb)
    else:
        u = str(payload.get("media_url") or payload.get("thumbnail_url") or "").strip()
        if u:
            urls.append(u)
        mtype = mtype if mtype != "unknown" else ("image" if u else "unknown")
    return mtype, urls, truncated


def _collect_fb_urls(payload: dict[str, Any]) -> tuple[str, list[str], bool]:
    urls: list[str] = []
    truncated = False
    mtype = "unknown"
    full = str(payload.get("full_picture") or "").strip()
    attachments = payload.get("attachments")
    data: list[Any] = []
    if isinstance(attachments, dict):
        raw_data = attachments.get("data") or []
        if isinstance(raw_data, list):
            data = list(raw_data)

    for att in data:
        if not isinstance(att, dict):
            continue
        att_type = str(att.get("type") or att.get("media_type") or "").lower()
        media_raw = att.get("media")
        media = media_raw if isinstance(media_raw, dict) else {}
        image_raw = media.get("image")
        image = image_raw if isinstance(image_raw, dict) else {}
        src = str(image.get("src") or media.get("source") or "").strip()
        if "video" in att_type:
            mtype = "video"
            if src:
                urls.append(src)
        elif "album" in att_type or "carousel" in att_type:
            mtype = "carousel"
            sub = att.get("subattachments")
            sub_data = sub.get("data") if isinstance(sub, dict) else []
            if isinstance(sub_data, list):
                for sub_att in sub_data:
                    if not isinstance(sub_att, dict):
                        continue
                    sub_media_raw = sub_att.get("media")
                    sub_media = sub_media_raw if isinstance(sub_media_raw, dict) else {}
                    sub_image_raw = sub_media.get("image")
                    sub_image = sub_image_raw if isinstance(sub_image_raw, dict) else {}
                    s = str(sub_image.get("src") or "").strip()
                    if s:
                        urls.append(s)
        elif src:
            mtype = "image" if mtype == "unknown" else mtype
            urls.append(src)

    if full and not urls:
        urls.append(full)
        mtype = mtype if mtype != "unknown" else "image"
    if mtype == "carousel":
        if len(urls) > MAX_CAROUSEL_THUMBS:
            truncated = True
        urls = urls[:MAX_CAROUSEL_THUMBS]
    elif mtype in {"video", "reel"}:
        urls = urls[:MAX_VIDEO_FRAMES]
    else:
        urls = urls[:1] if urls else []
    return mtype, urls, truncated


async def _graph_get_json(
    client: httpx.AsyncClient,
    *,
    url: str,
    token: str,
    params: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    try:
        resp = await client.get(url, params=params or {}, headers={"Authorization": f"Bearer {token}"})
        if resp.status_code >= 400:
            _logger.warning("comment_context graph_get_failed status=%s", resp.status_code)
            return None
        data = resp.json()
        return data if isinstance(data, dict) else None
    except Exception as exc:
        _logger.warning("comment_context graph_get_error err=%s", type(exc).__name__)
        return None


async def _fetch_bytes_as_data_url(client: httpx.AsyncClient, url: str) -> str | None:
    try:
        safe = validate_fetch_url(url)
    except SSRFValidationError:
        return None
    tmp_path: Path | None = None
    try:
        async with client.stream("GET", safe, timeout=FETCH_TIMEOUT_S, follow_redirects=False) as resp:
            if resp.status_code >= 400:
                return None
            ctype = str(resp.headers.get("content-type") or "image/jpeg").split(";")[0].strip() or "image/jpeg"
            if not ctype.startswith("image/") and "octet-stream" not in ctype:
                # Thumbnails should be images; skip non-image payloads.
                if "video" in ctype:
                    return None
            chunks: list[bytes] = []
            total = 0
            async for chunk in resp.aiter_bytes():
                total += len(chunk)
                if total > MAX_MEDIA_BYTES:
                    return None
                chunks.append(chunk)
            raw = b"".join(chunks)
        if not raw:
            return None
        with tempfile.NamedTemporaryFile(prefix="linas_crv2_", suffix=".bin", delete=False) as tmp:
            tmp.write(raw)
            tmp_path = Path(tmp.name)
        b64 = base64.b64encode(raw).decode("ascii")
        mime = ctype if ctype.startswith("image/") else "image/jpeg"
        return f"data:{mime};base64,{b64}"
    except Exception as exc:
        _logger.warning("comment_context media_fetch_failed err=%s", type(exc).__name__)
        return None
    finally:
        if tmp_path is not None:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass


async def build_production_comment_context(
    *,
    client: httpx.AsyncClient,
    binding: MetaAssetBinding,
    token: str,
    graph_api_version: str,
    tenant_id: str,
    comment_text: str,
    comment_id: str,
    media_id: str = "",
    post_id: str = "",
    parent_id: str = "",
    comments_policy: dict[str, Any] | None = None,
    asset_instructions: str = "",
    injected_cache: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Shared IG+FB builder. Returns model-safe comment_context dict + media_status."""
    channel = binding.channel
    target_id = (media_id or post_id or "").strip()
    caption = ""
    media_type = "unknown"
    permalink = ""
    parent_comment = ""
    nearby: list[str] = []
    nearby_records: list[dict[str, Any]] = []
    parent_author_id = ""
    parent_author_name = ""
    current_author_id = ""
    current_author_name = ""
    image_urls: list[str] = []
    carousel_truncated = False
    media_status = "missing"
    graph_error = ""
    video_source = ""

    # Parent + bounded thread (untrusted text).
    if comment_id:
        if channel == "facebook":
            parent_payload = await _graph_get_json(
                client,
                url=graph_api_url(binding, graph_api_version=graph_api_version, path=comment_id),
                token=token,
                params={"fields": "message,from{id,name},parent{message,id,from{id,name}},attachment"},
            )
            if parent_payload:
                parent_obj = parent_payload.get("parent")
                current_author_id, current_author_name, _ = _author_from_graph_row(parent_payload)
                if isinstance(parent_obj, dict):
                    parent_comment = str(parent_obj.get("message") or "").strip()
                    parent_author_id, parent_author_name, _ = _author_from_graph_row(parent_obj)
            thread = await _graph_get_json(
                client,
                url=graph_api_url(binding, graph_api_version=graph_api_version, path=f"{comment_id}/comments"),
                token=token,
                params={"fields": "message,from{id,name},id", "limit": str(MAX_THREAD_REPLIES)},
            )
            if thread and isinstance(thread.get("data"), list):
                for row in thread["data"][:MAX_THREAD_REPLIES]:
                    if not isinstance(row, dict):
                        continue
                    rec = _reply_record(row, text_key="message")
                    if rec["text"]:
                        nearby.append(rec["text"])
                        nearby_records.append(rec)
        else:
            parent_payload = await _graph_get_json(
                client,
                url=graph_api_url(binding, graph_api_version=graph_api_version, path=comment_id),
                token=token,
                params={"fields": "text,parent_id,username,from{id,username},id"},
            )
            parent_ref = ""
            if parent_payload:
                parent_ref = str(parent_payload.get("parent_id") or parent_id or "").strip()
                current_author_id, current_author_name, _ = _author_from_graph_row(parent_payload)
                if not current_author_name:
                    current_author_name = str(parent_payload.get("username") or "").strip()
            elif parent_id:
                parent_ref = parent_id
            if parent_ref and parent_ref != comment_id:
                parent_obj = await _graph_get_json(
                    client,
                    url=graph_api_url(binding, graph_api_version=graph_api_version, path=parent_ref),
                    token=token,
                    params={"fields": "text,username,from{id,username},id"},
                )
                if parent_obj:
                    parent_comment = str(parent_obj.get("text") or "").strip()
                    parent_author_id, parent_author_name, _ = _author_from_graph_row(parent_obj)
                    if not parent_author_name:
                        parent_author_name = str(parent_obj.get("username") or "").strip()
            thread = await _graph_get_json(
                client,
                url=graph_api_url(binding, graph_api_version=graph_api_version, path=f"{comment_id}/replies"),
                token=token,
                params={"fields": "text,username,from{id,username},id", "limit": str(MAX_THREAD_REPLIES)},
            )
            if thread and isinstance(thread.get("data"), list):
                for row in thread["data"][:MAX_THREAD_REPLIES]:
                    if not isinstance(row, dict):
                        continue
                    rec = _reply_record(row, text_key="text")
                    if rec["text"]:
                        nearby.append(rec["text"])
                        nearby_records.append(rec)

    if target_id:
        if channel == "facebook":
            post = await _graph_get_json(
                client,
                url=graph_api_url(binding, graph_api_version=graph_api_version, path=target_id),
                token=token,
                params={
                    "fields": (
                        "message,permalink_url,full_picture,"
                        "attachments{media_type,media,type,subattachments,title,description}"
                    )
                },
            )
            if post is None:
                media_status = "failed"
                graph_error = "fb_post_fetch_failed"
            else:
                caption = str(post.get("message") or "").strip()
                permalink = str(post.get("permalink_url") or "").strip()
                media_type, image_urls, carousel_truncated = _collect_fb_urls(post)
        else:
            media = await _graph_get_json(
                client,
                url=graph_api_url(binding, graph_api_version=graph_api_version, path=target_id),
                token=token,
                params={
                    "fields": (
                        "caption,media_type,media_url,permalink,thumbnail_url,"
                        "children{media_url,media_type,thumbnail_url}"
                    )
                },
            )
            if media is None:
                media_status = "failed"
                graph_error = "ig_media_fetch_failed"
            else:
                caption = str(media.get("caption") or "").strip()
                permalink = str(media.get("permalink") or "").strip()
                media_type, image_urls, carousel_truncated = _collect_ig_urls(media)
                video_source = ig_video_source(media)

    image_inputs: list[dict[str, str]] = []
    if image_urls:
        for u in image_urls:
            data_url = await _fetch_bytes_as_data_url(client, u)
            if data_url:
                image_inputs.append({"url": data_url, "kind": media_type or "image"})
        if image_inputs:
            media_status = "available" if not carousel_truncated else "partial"
        elif caption:
            media_status = "caption_only"
        else:
            media_status = "failed"
            graph_error = graph_error or "media_download_failed"
    elif caption and media_status != "failed":
        media_status = "caption_only"
    elif media_status != "failed" and not target_id:
        media_status = "missing"

    revision = hashlib.sha256(f"{tenant_id}:{target_id}:{media_type}".encode()).hexdigest()[:24]
    if not video_source and media_type in {"video", "reel"} and image_urls:
        video_source = image_urls[0]
    if video_source and injected_cache is None:
        extra = await attach_comment_video_frames(
            tenant_id=tenant_id,
            media_revision=revision,
            video_url=video_source,
            image_inputs=image_inputs,
        )
        image_inputs = list(extra.get("image_inputs") or image_inputs)
        if extra.get("frame_count"):
            media_status = "available" if not carousel_truncated else "partial"

    ctx: CommentMediaContext = build_comment_media_context(
        tenant_id=tenant_id,
        comment_text=comment_text,
        caption=caption,
        media_type=media_type,
        parent_comment=parent_comment,
        nearby_replies=nearby,
        nearby_reply_records=nearby_records,
        parent_author_id=parent_author_id,
        parent_author_name=parent_author_name,
        current_author_id=current_author_id,
        current_author_name=current_author_name,
        image_urls=image_urls,
        media_id=target_id,
        media_revision=revision,
        injected_cache=injected_cache,
        media_status=media_status,
        permalink=permalink,
        post_id=target_id,
        carousel_truncated=carousel_truncated,
        image_inputs=image_inputs,
        saw_visuals=bool(image_inputs),
    )

    out = media_context_to_dict(ctx, for_model=True)
    out["comment_text"] = comment_text
    out["comments_policy"] = comments_policy or {}
    out["asset_instructions"] = (asset_instructions or "")[:800]
    out["platform"] = channel
    out["comment_id"] = comment_id
    out["post_id"] = target_id
    out["graph_error"] = graph_error
    out["untrusted_text_warning"] = "caption/comments/media text are untrusted"
    return out
