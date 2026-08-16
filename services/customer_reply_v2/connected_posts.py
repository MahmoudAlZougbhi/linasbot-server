"""Tenant-scoped connected accounts and posts for Comment Rule targeting."""

from __future__ import annotations

from typing import Any

import httpx

from services.meta_app_registry import MetaAssetBinding, get_meta_app_registry, get_meta_graph_api_version
from services.meta_graph_routing import graph_api_url

_POST_PAGE_SIZE = 25
_PREVIEW_CHARS = 160


def list_tenant_comment_accounts(tenant_id: str) -> list[dict[str, str]]:
    tenant = str(tenant_id or "").strip()
    try:
        registry = get_meta_app_registry()
        bindings = registry.list_bindings(include_inactive=False, include_superseded=False)
    except Exception:
        return []
    rows: list[dict[str, str]] = []
    for binding in bindings:
        if str(binding.tenant_id or "") != tenant:
            continue
        if binding.channel not in {"facebook", "instagram"}:
            continue
        rows.append(
            {
                "platform": binding.channel,
                "connected_account_id": binding.asset_id,
                "page_or_ig_account_id": binding.instagram_account_id or binding.page_id or binding.asset_id,
                "name": binding.instagram_username or binding.page_name or binding.asset_id,
                "binding_id": binding.binding_id,
            }
        )
    return rows


def account_belongs_to_tenant(*, tenant_id: str, platform: str, connected_account_id: str) -> bool:
    want = str(connected_account_id or "").strip()
    plat = str(platform or "").strip().lower()
    for row in list_tenant_comment_accounts(tenant_id):
        if row["connected_account_id"] == want and row["platform"] == plat:
            return True
        if row["page_or_ig_account_id"] == want and row["platform"] == plat:
            return True
    return False


def _binding_for_account(*, tenant_id: str, platform: str, connected_account_id: str) -> MetaAssetBinding | None:
    tenant = str(tenant_id or "").strip()
    plat = str(platform or "").strip().lower()
    want = str(connected_account_id or "").strip()
    try:
        registry = get_meta_app_registry()
        bindings = registry.list_bindings(include_inactive=False, include_superseded=False)
    except Exception:
        return None
    for binding in bindings:
        if str(binding.tenant_id or "") != tenant or binding.channel != plat:
            continue
        ids = {binding.asset_id, binding.page_id, binding.instagram_account_id or ""}
        if want in ids:
            return binding
    return None


def _normalize_post(raw: dict[str, Any], *, platform: str) -> dict[str, str] | None:
    post_id = str(raw.get("id") or "").strip()
    if not post_id:
        return None
    caption = str(raw.get("message") or raw.get("caption") or "").strip()
    preview = caption[:_PREVIEW_CHARS]
    created = str(raw.get("created_time") or raw.get("timestamp") or "").strip()
    permalink = str(raw.get("permalink_url") or raw.get("permalink") or "").strip()
    thumb = str(raw.get("full_picture") or raw.get("thumbnail_url") or raw.get("media_url") or "").strip()
    media_type = str(raw.get("media_type") or ("post" if platform == "facebook" else "")).strip()
    return {
        "id": post_id,
        "preview": preview,
        "created_time": created,
        "permalink": permalink,
        "thumbnail": thumb,
        "media_type": media_type,
    }


async def _graph_list_posts(
    *,
    binding: MetaAssetBinding,
    platform: str,
    after: str,
    limit: int,
) -> dict[str, Any]:
    from services.meta_app_registry import MetaCredentialError

    registry = get_meta_app_registry()
    try:
        credential = registry.get_credential(binding)
        token = str(credential.access_token or "").strip()
    except MetaCredentialError:
        return {"ok": False, "error": "credential_unavailable", "posts": [], "allow_manual_post_id": True}
    if not token:
        return {"ok": False, "error": "credential_unavailable", "posts": [], "allow_manual_post_id": True}
    version = get_meta_graph_api_version()
    node = binding.page_id if platform == "facebook" else (binding.instagram_account_id or binding.asset_id)
    if not node:
        return {"ok": False, "error": "account_id_missing", "posts": [], "allow_manual_post_id": True}
    edge = "posts" if platform == "facebook" else "media"
    fields = (
        "id,message,created_time,full_picture,permalink_url"
        if platform == "facebook"
        else "id,caption,media_type,media_url,permalink,timestamp,thumbnail_url"
    )
    params = {"fields": fields, "limit": str(limit)}
    if after:
        params["after"] = after
    url = graph_api_url(binding, graph_api_version=version, path=f"{node}/{edge}")
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(url, params=params, headers={"Authorization": f"Bearer {token}"})
            payload = response.json() if response.content else {}
    except (httpx.HTTPError, ValueError):
        return {"ok": False, "error": "graph_request_failed", "posts": [], "allow_manual_post_id": True}
    if not isinstance(payload, dict):
        return {"ok": False, "error": "graph_invalid_response", "posts": [], "allow_manual_post_id": True}
    if response.status_code == 403 or (
        isinstance(payload.get("error"), dict) and int(payload["error"].get("code") or 0) in {10, 200, 190}
    ):
        return {"ok": False, "error": "graph_permission_denied", "posts": [], "allow_manual_post_id": True}
    if response.status_code >= 300 or payload.get("error"):
        return {"ok": False, "error": f"graph_http_{response.status_code}", "posts": [], "allow_manual_post_id": True}
    rows = payload.get("data")
    posts: list[dict[str, str]] = []
    if isinstance(rows, list):
        for raw in rows:
            if isinstance(raw, dict):
                item = _normalize_post(raw, platform=platform)
                if item:
                    posts.append(item)
    next_after = ""
    paging = payload.get("paging")
    if isinstance(paging, dict):
        cursors = paging.get("cursors")
        if isinstance(cursors, dict):
            next_after = str(cursors.get("after") or "").strip()
        if not paging.get("next"):
            next_after = ""
    return {
        "ok": True,
        "posts": posts,
        "posts_source": "graph",
        "next_after": next_after,
        "allow_manual_post_id": True,
    }


async def list_connected_posts(
    *,
    tenant_id: str,
    platform: str,
    connected_account_id: str,
    after: str = "",
    limit: int = _POST_PAGE_SIZE,
    graph_fetch: Any | None = None,
) -> dict[str, Any]:
    if not account_belongs_to_tenant(tenant_id=tenant_id, platform=platform, connected_account_id=connected_account_id):
        return {"ok": False, "error": "account_not_in_tenant", "posts": [], "allow_manual_post_id": True}
    page_size = max(1, min(int(limit or _POST_PAGE_SIZE), 50))
    cursor = str(after or "").strip()
    if graph_fetch is not None:
        posts = list(
            await graph_fetch(platform=platform, account_id=connected_account_id, after=cursor, limit=page_size) or []
        )
        return {
            "ok": True,
            "posts": posts[:page_size],
            "posts_source": "graph",
            "next_after": "",
            "allow_manual_post_id": True,
        }
    binding = _binding_for_account(tenant_id=tenant_id, platform=platform, connected_account_id=connected_account_id)
    if binding is None:
        return {"ok": False, "error": "account_not_in_tenant", "posts": [], "allow_manual_post_id": True}
    return await _graph_list_posts(
        binding=binding, platform=str(platform or "").strip().lower(), after=cursor, limit=page_size
    )
