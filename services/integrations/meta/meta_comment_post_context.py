"""Attach the real Meta post id, caption, and parent comment before AI/rules run."""

from __future__ import annotations

import time
from typing import Any

import httpx

from services.integrations.meta.meta_app_registry import MetaAssetBinding
from services.integrations.meta.meta_graph_routing import graph_api_url

_CAPTION_TTL_SECONDS = 600.0
_POST_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


def _cache_get(key: str) -> dict[str, Any] | None:
    row = _POST_CACHE.get(key)
    if not row:
        return None
    stored_at, payload = row
    if time.time() - stored_at > _CAPTION_TTL_SECONDS:
        _POST_CACHE.pop(key, None)
        return None
    return dict(payload)


def _cache_put(key: str, payload: dict[str, Any]) -> None:
    _POST_CACHE[key] = (time.time(), dict(payload))
    if len(_POST_CACHE) < 400:
        return
    cutoff = time.time() - _CAPTION_TTL_SECONDS
    stale = [item for item, (ts, _) in _POST_CACHE.items() if ts < cutoff]
    for item in stale:
        _POST_CACHE.pop(item, None)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _is_site_permalink(url: str) -> bool:
    lowered = (url or "").strip().lower()
    return any(token in lowered for token in ("instagram.com/", "facebook.com/", "fb.com/", "fb.watch"))


def _is_video_type(media_type: str) -> bool:
    label = (media_type or "").strip().upper()
    return label in {"VIDEO", "REEL", "STORY"} or "VIDEO" in label or "REEL" in label


def _caption_from_payload(payload: dict[str, Any]) -> str:
    return str(payload.get("caption") or payload.get("message") or payload.get("story") or "").strip()


def _media_type_from_payload(payload: dict[str, Any]) -> str:
    return str(payload.get("media_type") or payload.get("type") or "").strip()


def _image_urls_from_payload(payload: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    keys = ("thumbnail_url", "full_picture")
    media_url = str(payload.get("media_url") or "").strip()
    if media_url and not _is_video_type(_media_type_from_payload(payload)) and not _is_site_permalink(media_url):
        urls.append(media_url)
    for key in keys:
        value = str(payload.get(key) or "").strip()
        if value and value not in urls and not _is_site_permalink(value):
            urls.append(value)
    return urls


def _video_url_from_payload(payload: dict[str, Any]) -> str:
    if not _is_video_type(_media_type_from_payload(payload)):
        return ""
    media_url = str(payload.get("media_url") or "").strip()
    if media_url and not _is_site_permalink(media_url):
        return media_url
    return ""


def _post_id_from_comment_payload(payload: dict[str, Any], *, channel: str) -> str:
    if channel == "instagram":
        media = _as_dict(payload.get("media"))
        return str(media.get("id") or payload.get("media_id") or "").strip()
    post = _as_dict(payload.get("post"))
    return str(post.get("id") or payload.get("post_id") or "").strip()


def _parent_text_from_payload(payload: dict[str, Any]) -> str:
    parent = payload.get("parent")
    if isinstance(parent, dict):
        return str(parent.get("message") or parent.get("text") or "").strip()
    return ""


async def _graph_get(
    client: httpx.AsyncClient,
    url: str,
    *,
    token: str,
    params: dict[str, str],
) -> dict[str, Any] | None:
    try:
        response = await client.get(url, params=params, headers={"Authorization": f"Bearer {token}"})
    except httpx.HTTPError:
        return None
    if response.status_code < 200 or response.status_code >= 300:
        return None
    try:
        payload = response.json()
    except ValueError:
        return None
    if not isinstance(payload, dict) or payload.get("error"):
        return None
    return payload


async def _fetch_comment_graph(
    client: httpx.AsyncClient,
    *,
    binding: MetaAssetBinding,
    comment_id: str,
    token: str,
    graph_api_version: str,
) -> dict[str, Any] | None:
    if binding.channel == "instagram":
        fields = "media{id,caption,media_type,media_url,thumbnail_url},parent_id,text,id"
    else:
        fields = "post{id,message,story,full_picture},parent{id,message},message,id"
    return await _graph_get(
        client,
        graph_api_url(binding, graph_api_version=graph_api_version, path=comment_id),
        token=token,
        params={"fields": fields},
    )


async def _fetch_post_context(
    client: httpx.AsyncClient,
    *,
    binding: MetaAssetBinding,
    post_id: str,
    token: str,
    graph_api_version: str,
) -> dict[str, Any]:
    cache_key = f"{binding.binding_id}:{post_id}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    fields = (
        "caption,media_type,media_url,thumbnail_url" if binding.channel == "instagram" else "message,story,full_picture"
    )
    payload = await _graph_get(
        client,
        graph_api_url(binding, graph_api_version=graph_api_version, path=post_id),
        token=token,
        params={"fields": fields},
    )
    body = payload or {}
    out = {
        "caption": _caption_from_payload(body),
        "media_type": _media_type_from_payload(body),
        "image_urls": _image_urls_from_payload(body),
        "video_url": _video_url_from_payload(body),
    }
    _cache_put(cache_key, out)
    return out


async def enrich_comment_event_post(
    event: dict[str, Any],
    *,
    binding: MetaAssetBinding,
    token: str,
    graph_api_version: str,
    client: httpx.AsyncClient | None = None,
    allow_graph: bool = True,
) -> dict[str, Any]:
    """Fill post_id / caption / parent_comment / media from Graph when the webhook omitted them."""

    out = dict(event)
    comment_id = str(out.get("comment_id") or "").strip()
    post_id = str(out.get("post_id") or out.get("media_id") or "").strip()
    caption = str(out.get("caption") or out.get("post_caption") or "").strip()
    parent_comment = str(out.get("parent_comment") or out.get("parent_text") or "").strip()
    parent_id = str(out.get("parent_id") or "").strip()
    media_type = str(out.get("media_type") or "").strip()
    image_urls = [str(item).strip() for item in (out.get("image_urls") or []) if str(item).strip()]
    video_url = str(out.get("video_url") or "").strip()
    if post_id:
        out["post_id"] = post_id
        out["media_id"] = str(out.get("media_id") or post_id)
    if not allow_graph or not str(token or "").strip():
        return out
    if not comment_id and not post_id:
        return out

    owns_client = client is None
    graph = client or httpx.AsyncClient(timeout=15.0)
    try:
        need_comment = bool(comment_id) and (
            (not post_id) or (parent_id and parent_id != post_id and not parent_comment)
        )
        comment_payload = None
        if need_comment:
            comment_payload = await _fetch_comment_graph(
                graph,
                binding=binding,
                comment_id=comment_id,
                token=token,
                graph_api_version=graph_api_version,
            )
        if comment_payload:
            graph_post = _post_id_from_comment_payload(comment_payload, channel=binding.channel)
            if graph_post:
                post_id = graph_post
            media = _as_dict(comment_payload.get("media"))
            post_obj = _as_dict(comment_payload.get("post"))
            if not caption:
                caption = _caption_from_payload(media) or _caption_from_payload(post_obj)
            if not media_type:
                media_type = _media_type_from_payload(media) or _media_type_from_payload(post_obj)
            for url in _image_urls_from_payload(media) + _image_urls_from_payload(post_obj):
                if url not in image_urls:
                    image_urls.append(url)
            video_url = video_url or _video_url_from_payload(media) or _video_url_from_payload(post_obj)
            if not parent_comment:
                parent_comment = _parent_text_from_payload(comment_payload)
        if post_id and (
            not caption or not media_type or not image_urls or (_is_video_type(media_type) and not video_url)
        ):
            post_ctx = await _fetch_post_context(
                graph,
                binding=binding,
                post_id=post_id,
                token=token,
                graph_api_version=graph_api_version,
            )
            caption = caption or str(post_ctx.get("caption") or "")
            media_type = media_type or str(post_ctx.get("media_type") or "")
            for url in list(post_ctx.get("image_urls") or []):
                value = str(url or "").strip()
                if value and value not in image_urls:
                    image_urls.append(value)
            video_url = video_url or str(post_ctx.get("video_url") or "").strip()
    finally:
        if owns_client:
            await graph.aclose()

    if post_id:
        out["post_id"] = post_id
        out["media_id"] = str(out.get("media_id") or post_id)
    if caption:
        out["caption"] = caption
        out["post_caption"] = caption
    if media_type:
        out["media_type"] = media_type
    if image_urls:
        out["image_urls"] = image_urls
    if video_url:
        out["video_url"] = video_url
    if parent_comment:
        out["parent_comment"] = parent_comment
    return out
