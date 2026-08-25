"""Poll Meta Graph for new Page/Instagram comments when webhooks are absent."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from services.meta_app_registry import APP_A_KEY, MetaAssetBinding, get_meta_app_configs, get_meta_app_registry
from services.meta_comment_events import ResolvedMetaCommentEvent
from services.meta_comment_reply_settings import get_comment_reply_setting
from services.meta_comment_sync_cursors import (
    extract_next_cursor,
    load_posts_backfill_cursor,
    load_seen_comment_ids,
    save_posts_backfill_cursor,
    save_seen_comment_ids,
)
from services.meta_graph_routing import build_messaging_settings_for_binding, graph_api_url

_runtime_logger = logging.getLogger("uvicorn.error")
_MAX_POSTS_PER_SYNC = 25
_MAX_COMMENTS_PER_POST = 25
_MAX_COMMENT_NEST_DEPTH = 4
_GRAPH_RATE_LIMIT_BACKOFF_SECONDS = 2.0
_FACEBOOK_POST_COMMENT_FIELDS = (
    "comments.limit(25){id,message,from,created_time,"
    "comments.limit(20){id,message,from,created_time,"
    "comments.limit(15){id,message,from,created_time}}}"
)


def _binding_by_id(registry: Any, binding_id: str) -> MetaAssetBinding | None:
    target = str(binding_id or "").strip()
    if not target:
        return None
    for binding in registry.list_bindings(include_inactive=True, include_superseded=True):
        if binding.binding_id == target:
            return binding if isinstance(binding, MetaAssetBinding) else None
    return None


def _comment_reply_enabled(binding: MetaAssetBinding) -> bool:
    from services.cm.actions import comments_enforcement_decision

    registry = get_meta_app_registry()
    fresh = _binding_by_id(registry, binding.binding_id) or binding
    setting = get_comment_reply_setting(
        tenant_id=fresh.tenant_id,
        app_key=fresh.app_key,
        channel=fresh.channel,
        asset_id=fresh.asset_id,
    )
    try:
        credential = registry.get_credential(fresh)
    except Exception:
        return False
    decision = comments_enforcement_decision(
        tenant_id=fresh.tenant_id,
        channel=fresh.channel,
        per_asset_enabled=bool(setting.enabled),
        binding=fresh,
        credential=credential,
        registry=registry,
    )
    return bool(decision["allow"])


def _iter_facebook_comment_nodes(comments: list[dict[str, Any]], *, depth: int = 0) -> list[dict[str, Any]]:
    """Flatten top-level and nested thread replies from one post's comment tree."""

    nodes: list[dict[str, Any]] = []
    for raw in comments[:_MAX_COMMENTS_PER_POST]:
        if not isinstance(raw, dict):
            continue
        nodes.append(raw)
        if depth >= _MAX_COMMENT_NEST_DEPTH:
            continue
        nested = (raw.get("comments") or {}).get("data") if isinstance(raw.get("comments"), dict) else []
        if isinstance(nested, list) and nested:
            nodes.extend(_iter_facebook_comment_nodes(nested, depth=depth + 1))
    return nodes


def _facebook_comment_events(post_id: str, comments: list[dict[str, Any]], *, page_id: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for raw in _iter_facebook_comment_nodes(comments):
        comment_id = str(raw.get("id") or "").strip()
        from_raw = raw.get("from")
        from_dict = from_raw if isinstance(from_raw, dict) else {}
        author_id = str(from_dict.get("id") or "").strip()
        text = str(raw.get("message") or "").strip()
        if not comment_id or not author_id or not text:
            continue
        if author_id == page_id:
            continue
        events.append(
            {
                "channel": "facebook",
                "comment_id": comment_id,
                "post_id": post_id,
                "media_id": post_id,
                "author_id": author_id,
                "author_name": str(from_dict.get("name") or "").strip(),
                "text": text,
                "message_id": comment_id,
                "account_id": page_id,
            }
        )
    return events


def _mark_comment_seen(*, binding_id: str, post_id: str, comment_id: str) -> None:
    post_key = str(post_id or "").strip()
    comment_key = str(comment_id or "").strip()
    if not post_key or not comment_key:
        return
    seen = load_seen_comment_ids(binding_id, post_key)
    seen.add(comment_key)
    save_seen_comment_ids(binding_id, post_key, seen)


async def _process_facebook_posts_payload(
    posts_payload: dict[str, Any],
    *,
    binding: MetaAssetBinding,
    settings: Any,
    page_id: str,
    seen_post_ids: set[str],
) -> tuple[int, int]:
    discovered = 0
    enqueued = 0
    posts_raw = posts_payload.get("data")
    posts: list[Any] = posts_raw if isinstance(posts_raw, list) else []
    for post in posts:
        if not isinstance(post, dict):
            continue
        post_id = str(post.get("id") or "").strip()
        if not post_id or post_id in seen_post_ids:
            continue
        seen_post_ids.add(post_id)
        comments = (post.get("comments") or {}).get("data") if isinstance(post.get("comments"), dict) else []
        if not isinstance(comments, list):
            comments = []
        seen_comment_ids = load_seen_comment_ids(binding.binding_id, post_id)
        handled_this_pass: set[str] = set()
        for event in _facebook_comment_events(post_id, comments, page_id=page_id):
            comment_id = str(event.get("comment_id") or "").strip()
            if comment_id in seen_comment_ids or comment_id in handled_this_pass:
                continue
            handled_this_pass.add(comment_id)
            discovered += 1
            if await _enqueue_comment_ai(binding=binding, settings=settings, event=event):
                enqueued += 1
    return discovered, enqueued


async def _graph_get_json(
    client: httpx.AsyncClient,
    *,
    binding: MetaAssetBinding,
    token: str,
    path: str,
    params: dict[str, str] | None = None,
    absolute_url: str | None = None,
) -> dict[str, Any]:
    app = get_meta_app_configs()[binding.app_key]
    if absolute_url:
        response = await client.get(absolute_url, params={"access_token": token})
    else:
        url = graph_api_url(binding, graph_api_version=app.graph_api_version, path=path)
        response = await client.get(url, params={"access_token": token, **(params or {})})
    if response.status_code == 429:
        import asyncio

        await asyncio.sleep(_GRAPH_RATE_LIMIT_BACKOFF_SECONDS)
        if absolute_url:
            response = await client.get(absolute_url, params={"access_token": token})
        else:
            url = graph_api_url(binding, graph_api_version=app.graph_api_version, path=path)
            response = await client.get(url, params={"access_token": token, **(params or {})})
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise TypeError("meta_graph_response_invalid")
    return payload


async def sync_facebook_binding_comments(binding_id: str) -> dict[str, Any]:
    registry = get_meta_app_registry()
    binding = _binding_by_id(registry, binding_id)
    if binding is None or not binding.active or binding.status != "active":
        return {"skipped": True, "reason": "binding_inactive"}
    if binding.channel != "facebook" or binding.app_key != APP_A_KEY:
        return {"skipped": True, "reason": "not_facebook_app_a"}
    if not _comment_reply_enabled(binding):
        return {"skipped": True, "reason": "comments_disabled"}
    credential = registry.get_credential(binding)
    app = get_meta_app_configs()[binding.app_key]
    settings = build_messaging_settings_for_binding(binding, credential=credential, app_config=app)
    token = credential.access_token
    page_id = binding.page_id
    discovered = 0
    enqueued = 0
    posts_params = {
        "fields": f"id,{_FACEBOOK_POST_COMMENT_FIELDS}",
        "limit": str(_MAX_POSTS_PER_SYNC),
    }

    async with httpx.AsyncClient(timeout=25.0) as client:
        seen_post_ids: set[str] = set()
        recent_payload = await _graph_get_json(
            client,
            binding=binding,
            token=token,
            path=f"{page_id}/posts",
            params=posts_params,
        )
        recent_discovered, recent_enqueued = await _process_facebook_posts_payload(
            recent_payload,
            binding=binding,
            settings=settings,
            page_id=page_id,
            seen_post_ids=seen_post_ids,
        )
        discovered += recent_discovered
        enqueued += recent_enqueued

        posts_url = load_posts_backfill_cursor(binding.binding_id)
        if posts_url:
            backfill_payload = await _graph_get_json(
                client,
                binding=binding,
                token=token,
                path=f"{page_id}/posts",
                params=posts_params,
                absolute_url=posts_url,
            )
            backfill_discovered, backfill_enqueued = await _process_facebook_posts_payload(
                backfill_payload,
                binding=binding,
                settings=settings,
                page_id=page_id,
                seen_post_ids=seen_post_ids,
            )
            discovered += backfill_discovered
            enqueued += backfill_enqueued
            next_posts = extract_next_cursor(backfill_payload)
        else:
            next_posts = extract_next_cursor(recent_payload)
        save_posts_backfill_cursor(binding.binding_id, next_posts or "")

    _runtime_logger.info(
        "[meta-comment-sync] facebook binding=%s discovered=%d enqueued=%d",
        binding.binding_id[:8],
        discovered,
        enqueued,
    )
    return {"ok": True, "discovered": discovered, "enqueued": enqueued}


async def _enqueue_comment_ai(*, binding: MetaAssetBinding, settings: Any, event: dict[str, Any]) -> bool:
    comment_id = str(event.get("comment_id") or "").strip()
    post_id = str(event.get("post_id") or event.get("media_id") or "").strip()
    if not comment_id:
        return False
    from services.durable_event_claim import (
        complete_event_claim,
        meta_claim_binding_digest,
        release_event_claim,
        try_claim_event_handle,
    )
    from services.meta_comment_replies import process_meta_comment_event
    from services.meta_cross_flow_dedup import global_comment_claim_key
    from services.scale.meta_ingress import enqueue_meta_inbound_event, persist_meta_comment_accepted

    global_key = global_comment_claim_key(event)
    tagged = dict(event)
    tagged.update(
        {
            "tenant_id": binding.tenant_id,
            "meta_app_key": binding.app_key,
            "meta_binding_id": binding.binding_id,
            "meta_auth_flow": binding.auth_flow,
        }
    )
    resolved = ResolvedMetaCommentEvent(event=tagged, settings=settings, binding=binding)
    event_id, _created = persist_meta_comment_accepted(resolved, global_key=global_key)
    claim_handle = await try_claim_event_handle(
        "meta_social_comment_global",
        global_key,
        ttl_seconds=600.0,
        firestore_collection="meta_social_comment_global_claims",
        firestore_claim_metadata={
            "binding_id_sha256": meta_claim_binding_digest(binding.binding_id),
            "inbound_event_id": event_id,
        },
        meta_binding_id=binding.binding_id,
    )
    if claim_handle is None:
        return False

    dispatch = enqueue_meta_inbound_event(event_id, claim_handle=claim_handle)
    if dispatch == "queued":
        _mark_comment_seen(binding_id=binding.binding_id, post_id=post_id, comment_id=comment_id)
        return True
    if dispatch == "ambiguous":
        await release_event_claim(
            "meta_social_comment_global",
            global_key,
            firestore_collection="meta_social_comment_global_claims",
            claim_handle=claim_handle,
        )
        return False

    result = await process_meta_comment_event(resolved, inbound_event_id=event_id, simulation=False)
    if result.status in {"sent", "sent_dm"}:
        await complete_event_claim(
            "meta_social_comment_global",
            global_key,
            firestore_collection="meta_social_comment_global_claims",
            claim_handle=claim_handle,
        )
        _mark_comment_seen(binding_id=binding.binding_id, post_id=post_id, comment_id=comment_id)
        return True
    if result.status == "ignored" and result.reason in {"already_replied", "human_replied"}:
        await complete_event_claim(
            "meta_social_comment_global",
            global_key,
            firestore_collection="meta_social_comment_global_claims",
            claim_handle=claim_handle,
        )
        _mark_comment_seen(binding_id=binding.binding_id, post_id=post_id, comment_id=comment_id)
        return False
    if result.status == "ignored":
        await complete_event_claim(
            "meta_social_comment_global",
            global_key,
            firestore_collection="meta_social_comment_global_claims",
            claim_handle=claim_handle,
        )
        _mark_comment_seen(binding_id=binding.binding_id, post_id=post_id, comment_id=comment_id)
        return False
    await release_event_claim(
        "meta_social_comment_global",
        global_key,
        firestore_collection="meta_social_comment_global_claims",
        claim_handle=claim_handle,
    )
    _runtime_logger.warning(
        "[meta-comment-sync] process_skipped channel=%s comment=%s status=%s reason=%s",
        binding.channel,
        comment_id[-12:],
        result.status,
        result.reason,
    )
    return False


async def sync_instagram_binding_comments(binding_id: str) -> dict[str, Any]:
    registry = get_meta_app_registry()
    binding = _binding_by_id(registry, binding_id)
    if binding is None or not binding.active or binding.status != "active":
        return {"skipped": True, "reason": "binding_inactive"}
    if binding.channel != "instagram" or binding.app_key != APP_A_KEY:
        return {"skipped": True, "reason": "not_instagram_app_a"}
    if binding.auth_flow != "instagram_login":
        return {"skipped": True, "reason": "unsupported_auth_flow"}
    if not _comment_reply_enabled(binding):
        return {"skipped": True, "reason": "comments_disabled"}
    credential = registry.get_credential(binding)
    app = get_meta_app_configs()[binding.app_key]
    settings = build_messaging_settings_for_binding(binding, credential=credential, app_config=app)
    token = credential.access_token
    ig_id = binding.instagram_account_id or binding.asset_id
    discovered = 0
    enqueued = 0

    async with httpx.AsyncClient(timeout=25.0) as client:
        media_payload = await _graph_get_json(
            client,
            binding=binding,
            token=token,
            path=f"{ig_id}/media",
            params={
                "fields": "id,caption,comments.limit(25){id,text,username,timestamp}",
                "limit": str(_MAX_POSTS_PER_SYNC),
            },
        )
        rows_raw = media_payload.get("data")
        rows: list[Any] = rows_raw if isinstance(rows_raw, list) else []
        for media in rows:
            if not isinstance(media, dict):
                continue
            media_id = str(media.get("id") or "").strip()
            if not media_id:
                continue
            comments = (media.get("comments") or {}).get("data") if isinstance(media.get("comments"), dict) else []
            if not isinstance(comments, list):
                comments = []
            for raw in comments[:_MAX_COMMENTS_PER_POST]:
                if not isinstance(raw, dict):
                    continue
                comment_id = str(raw.get("id") or "").strip()
                username = str(raw.get("username") or "").strip()
                text = str(raw.get("text") or "").strip()
                if not comment_id or not text:
                    continue
                if username and username.casefold() == str(binding.instagram_username or "").casefold():
                    continue
                from services.meta_comment_events import _stable_instagram_username_author_id

                author_id = _stable_instagram_username_author_id(username) if username else ""
                if not author_id:
                    continue
                event = {
                    "channel": "instagram",
                    "comment_id": comment_id,
                    "post_id": media_id,
                    "media_id": media_id,
                    "author_id": author_id,
                    "author_username": username,
                    "text": text,
                    "message_id": comment_id,
                    "account_id": ig_id,
                }
                discovered += 1
                if await _enqueue_comment_ai(binding=binding, settings=settings, event=event):
                    enqueued += 1

    _runtime_logger.info(
        "[meta-comment-sync] instagram binding=%s discovered=%d enqueued=%d",
        binding.binding_id[:8],
        discovered,
        enqueued,
    )
    return {"ok": True, "discovered": discovered, "enqueued": enqueued}
