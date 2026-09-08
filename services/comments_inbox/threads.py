"""Comment + AI-reply pairs for one post. Meta uses Graph; TikTok uses the store."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from services.comments_inbox.thread_pairs import nested_replies, pair_comment_threads, pair_tiktok_threads
from services.customer_reply_v2.connected_posts import list_tenant_comment_accounts
from services.meta_app_registry import MetaCredentialError, get_meta_app_registry
from services.meta_graph_routing import graph_api_url, graph_api_version_for_binding

_HYDRATE_REPLIES = 12


def _account(tenant_id: str, platform: str) -> dict[str, str] | None:
    plat = str(platform or "").strip().lower()
    for row in list_tenant_comment_accounts(tenant_id):
        if row.get("platform") == plat:
            return row
    return None


def _tiktok_threads(*, tenant_id: str, post_id: str, limit: int) -> list[dict[str, Any]]:
    from db.session import whatsapp_db_configured, whatsapp_session
    from services.tiktok_business.repository_content import TikTokContentRepository

    if not whatsapp_db_configured():
        return []
    with whatsapp_session() as session:
        rows = TikTokContentRepository(session).list_comments_inbox(tenant_id=tenant_id, limit=200)
    return pair_tiktok_threads(rows, post_id=post_id, limit=limit)


def _self_names(binding: Any) -> set[str]:
    names = {
        str(getattr(binding, "instagram_username", "") or "").strip().casefold(),
        str(getattr(binding, "page_name", "") or "").strip().casefold(),
    }
    return {name for name in names if name}


def _self_ids(binding: Any) -> set[str]:
    return {
        str(getattr(binding, "asset_id", "") or "").strip(),
        str(getattr(binding, "page_id", "") or "").strip(),
        str(getattr(binding, "instagram_account_id", "") or "").strip(),
    } - {""}


def _graph_error(payload: Any, status_code: int) -> str:
    err = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(err, dict) and (err.get("message") or err.get("code")):
        return "graph_error"
    if status_code >= 300:
        return f"graph_http_{status_code}"
    return ""


def _comment_field_sets(platform: str) -> tuple[str, ...]:
    if platform == "instagram":
        base = "id,text,username,timestamp,parent_id"
        return (f"{base},replies{{{base}}}", base, "id,text,username,timestamp")
    base = "id,message,from,created_time,parent"
    return (f"{base},comments{{id,message,from,created_time}}", base, "id,message,from,created_time")


async def _hydrate_replies(
    client: httpx.AsyncClient,
    *,
    binding: Any,
    version: str,
    token: str,
    platform: str,
    rows: list[dict[str, Any]],
) -> None:
    need = [row for row in rows if str(row.get("id") or "") and not nested_replies(row, platform=platform)]
    if not need:
        return
    edge = "replies" if platform == "instagram" else "comments"
    fields = _comment_field_sets(platform)[-1]
    key = "replies" if platform == "instagram" else "comments"

    async def one(row: dict[str, Any]) -> None:
        url = graph_api_url(binding, graph_api_version=version, path=f"{row['id']}/{edge}")
        try:
            resp = await client.get(
                url,
                params={"fields": fields, "limit": "20"},
                headers={"Authorization": f"Bearer {token}"},
            )
            payload = resp.json() if resp.content else {}
        except (httpx.HTTPError, ValueError):
            return
        data = payload.get("data") if isinstance(payload, dict) else None
        if isinstance(data, list):
            row[key] = {"data": [item for item in data if isinstance(item, dict)]}

    await asyncio.gather(*(one(row) for row in need[:_HYDRATE_REPLIES]))


async def _graph_threads(
    *,
    tenant_id: str,
    platform: str,
    post_id: str,
    limit: int,
) -> tuple[list[dict[str, Any]], str]:
    from services.customer_reply_v2.connected_posts import account_belongs_to_tenant

    account = _account(tenant_id, platform)
    if account is None:
        return [], "disconnected"
    if not account_belongs_to_tenant(
        tenant_id=tenant_id, platform=platform, connected_account_id=account["connected_account_id"]
    ):
        return [], "disconnected"
    registry = get_meta_app_registry()
    binding = None
    for item in registry.list_bindings(include_inactive=False, include_superseded=False):
        if item.tenant_id != tenant_id or item.channel != platform:
            continue
        binding = item
        break
    if binding is None:
        return [], "disconnected"
    try:
        token = str(registry.get_credential(binding).access_token or "").strip()
    except MetaCredentialError:
        return [], "credential_unavailable"
    if not token:
        return [], "credential_unavailable"
    version = graph_api_version_for_binding(binding)
    url = graph_api_url(binding, graph_api_version=version, path=f"{post_id}/comments")
    last_error = ""
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            for fields in _comment_field_sets(platform):
                resp = await client.get(
                    url,
                    params={"fields": fields, "limit": str(min(limit, 50))},
                    headers={"Authorization": f"Bearer {token}"},
                )
                payload = resp.json() if resp.content else {}
                last_error = _graph_error(payload, resp.status_code)
                if last_error or not isinstance(payload, dict):
                    continue
                raw = payload.get("data")
                rows = [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []
                await _hydrate_replies(
                    client,
                    binding=binding,
                    version=version,
                    token=token,
                    platform=platform,
                    rows=rows,
                )
                return (
                    pair_comment_threads(
                        rows,
                        platform=platform,
                        media_id=post_id,
                        names=_self_names(binding),
                        ids=_self_ids(binding),
                        limit=limit,
                    ),
                    "",
                )
    except (httpx.HTTPError, ValueError):
        return [], "graph_request_failed"
    return [], last_error or "graph_request_failed"


async def list_comment_threads(
    *,
    tenant_id: str,
    platform: str,
    post_id: str,
    limit: int = 50,
) -> dict[str, Any]:
    plat = str(platform or "").strip().lower()
    media_id = str(post_id or "").strip()
    if plat not in {"instagram", "facebook", "tiktok"} or not media_id:
        return {"ok": False, "status": "error", "error": "invalid", "threads": []}
    error = ""
    if plat == "tiktok":
        threads = _tiktok_threads(tenant_id=tenant_id, post_id=media_id, limit=limit)
    else:
        threads, error = await _graph_threads(tenant_id=tenant_id, platform=plat, post_id=media_id, limit=limit)
    if error and not threads:
        return {
            "ok": False,
            "status": "error",
            "error": error,
            "threads": [],
            "platform": plat,
            "post_id": media_id,
        }
    return {
        "ok": True,
        "status": "ok" if threads else "empty",
        "error": "",
        "threads": threads,
        "platform": plat,
        "post_id": media_id,
    }
