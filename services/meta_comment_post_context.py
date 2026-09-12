"""Attach the real Meta post id, caption, and parent comment before AI/rules run."""

from __future__ import annotations

import time
from typing import Any

import httpx

from services.meta_app_registry import MetaAssetBinding
from services.meta_graph_routing import graph_api_url

_CAPTION_TTL_SECONDS = 600.0
_CAPTION_CACHE: dict[str, tuple[float, str]] = {}


def _cache_get(key: str) -> str | None:
    row = _CAPTION_CACHE.get(key)
    if not row:
        return None
    stored_at, caption = row
    if time.time() - stored_at > _CAPTION_TTL_SECONDS:
        _CAPTION_CACHE.pop(key, None)
        return None
    return caption


def _cache_put(key: str, caption: str) -> None:
    _CAPTION_CACHE[key] = (time.time(), caption)
    if len(_CAPTION_CACHE) < 400:
        return
    cutoff = time.time() - _CAPTION_TTL_SECONDS
    stale = [item for item, (ts, _) in _CAPTION_CACHE.items() if ts < cutoff]
    for item in stale:
        _CAPTION_CACHE.pop(item, None)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _caption_from_payload(payload: dict[str, Any]) -> str:
    return str(payload.get("caption") or payload.get("message") or payload.get("story") or "").strip()


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
        fields = "media{id,caption},parent_id,text,id"
    else:
        fields = "post{id,message,story},parent{id,message},message,id"
    return await _graph_get(
        client,
        graph_api_url(binding, graph_api_version=graph_api_version, path=comment_id),
        token=token,
        params={"fields": fields},
    )


async def _fetch_post_caption(
    client: httpx.AsyncClient,
    *,
    binding: MetaAssetBinding,
    post_id: str,
    token: str,
    graph_api_version: str,
) -> str:
    cache_key = f"{binding.binding_id}:{post_id}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    fields = "caption" if binding.channel == "instagram" else "message,story"
    payload = await _graph_get(
        client,
        graph_api_url(binding, graph_api_version=graph_api_version, path=post_id),
        token=token,
        params={"fields": fields},
    )
    caption = _caption_from_payload(payload or {})
    _cache_put(cache_key, caption)
    return caption


async def enrich_comment_event_post(
    event: dict[str, Any],
    *,
    binding: MetaAssetBinding,
    token: str,
    graph_api_version: str,
    client: httpx.AsyncClient | None = None,
    allow_graph: bool = True,
) -> dict[str, Any]:
    """Fill post_id / caption / parent_comment from Graph when the webhook omitted them."""

    out = dict(event)
    comment_id = str(out.get("comment_id") or "").strip()
    post_id = str(out.get("post_id") or out.get("media_id") or "").strip()
    caption = str(out.get("caption") or out.get("post_caption") or "").strip()
    parent_comment = str(out.get("parent_comment") or out.get("parent_text") or "").strip()
    parent_id = str(out.get("parent_id") or "").strip()
    if post_id:
        out["post_id"] = post_id
        out["media_id"] = str(out.get("media_id") or post_id)
    if not allow_graph or not comment_id or not str(token or "").strip():
        return out

    owns_client = client is None
    graph = client or httpx.AsyncClient(timeout=15.0)
    try:
        need_comment = (not post_id) or (parent_id and parent_id != post_id and not parent_comment)
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
            if not caption:
                media = _as_dict(comment_payload.get("media"))
                post_obj = _as_dict(comment_payload.get("post"))
                caption = _caption_from_payload(media) or _caption_from_payload(post_obj)
            if not parent_comment:
                parent_comment = _parent_text_from_payload(comment_payload)
        if post_id and not caption:
            caption = await _fetch_post_caption(
                graph,
                binding=binding,
                post_id=post_id,
                token=token,
                graph_api_version=graph_api_version,
            )
    finally:
        if owns_client:
            await graph.aclose()

    if post_id:
        out["post_id"] = post_id
        out["media_id"] = str(out.get("media_id") or post_id)
    if caption:
        out["caption"] = caption
        out["post_caption"] = caption
    if parent_comment:
        out["parent_comment"] = parent_comment
    return out
