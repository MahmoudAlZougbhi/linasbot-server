"""Comment + AI-reply pairs for one post. Meta uses Graph; TikTok uses the store."""

from __future__ import annotations

from typing import Any

import httpx

from services.customer_reply_v2.connected_posts import list_tenant_comment_accounts
from services.meta_app_registry import MetaCredentialError, get_meta_app_registry, get_meta_graph_api_version
from services.meta_graph_routing import graph_api_url


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
    out: list[dict[str, Any]] = []
    for row in rows:
        if str(row.get("post_id") or "") != post_id:
            continue
        if str(row.get("delivery_status") or "") != "sent":
            continue
        reply = str(row.get("ai_reply") or "").strip()
        if not reply:
            continue
        out.append(
            {
                "comment_id": str(row.get("comment_id") or ""),
                "author": str(row.get("author_username") or ""),
                "comment": str(row.get("text") or ""),
                "ai_reply": reply,
                "created_at": str(row.get("create_time") or ""),
                "delivery_status": "sent",
            }
        )
        if len(out) >= limit:
            break
    return out


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


def _is_self(row: dict[str, Any], *, names: set[str], ids: set[str]) -> bool:
    from_candidate = row.get("from")
    from_raw = from_candidate if isinstance(from_candidate, dict) else {}
    username = str(row.get("username") or from_raw.get("username") or "").strip().casefold()
    from_id = str(from_raw.get("id") or "").strip()
    return username in names or from_id in ids


def _text_of(row: dict[str, Any]) -> str:
    return str(row.get("text") or row.get("message") or "").strip()


async def _graph_threads(
    *,
    tenant_id: str,
    platform: str,
    post_id: str,
    limit: int,
) -> list[dict[str, Any]]:
    from services.customer_reply_v2.connected_posts import account_belongs_to_tenant

    account = _account(tenant_id, platform)
    if account is None:
        return []
    if not account_belongs_to_tenant(
        tenant_id=tenant_id, platform=platform, connected_account_id=account["connected_account_id"]
    ):
        return []
    registry = get_meta_app_registry()
    binding = None
    for item in registry.list_bindings(include_inactive=False, include_superseded=False):
        if item.tenant_id != tenant_id or item.channel != platform:
            continue
        binding = item
        break
    if binding is None:
        return []
    try:
        token = str(registry.get_credential(binding).access_token or "").strip()
    except MetaCredentialError:
        return []
    if not token:
        return []
    version = get_meta_graph_api_version()
    fields = (
        "id,text,username,timestamp,replies{id,text,username,timestamp}"
        if platform == "instagram"
        else "id,message,from,created_time,comments{id,message,from,created_time}"
    )
    url = graph_api_url(binding, graph_api_version=version, path=f"{post_id}/comments")
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(
                url,
                params={"fields": fields, "limit": str(min(limit, 50))},
                headers={"Authorization": f"Bearer {token}"},
            )
            payload = resp.json() if resp.content else {}
    except (httpx.HTTPError, ValueError):
        return []
    if resp.status_code >= 300 or not isinstance(payload, dict) or payload.get("error"):
        return []
    names = _self_names(binding)
    ids = _self_ids(binding)
    out: list[dict[str, Any]] = []
    for raw in payload.get("data") or []:
        if not isinstance(raw, dict) or _is_self(raw, names=names, ids=ids):
            continue
        nested = raw.get("replies") if platform == "instagram" else raw.get("comments")
        replies = nested.get("data") if isinstance(nested, dict) else []
        if not isinstance(replies, list):
            continue
        ai_reply = ""
        for reply in replies:
            if isinstance(reply, dict) and _is_self(reply, names=names, ids=ids):
                ai_reply = _text_of(reply)
                if ai_reply:
                    break
        if not ai_reply:
            continue
        out.append(
            {
                "comment_id": str(raw.get("id") or ""),
                "author": str(raw.get("username") or (raw.get("from") or {}).get("name") or ""),
                "comment": _text_of(raw),
                "ai_reply": ai_reply,
                "created_at": str(raw.get("timestamp") or raw.get("created_time") or ""),
                "delivery_status": "sent",
            }
        )
        if len(out) >= limit:
            break
    return out


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
        return {"ok": False, "status": "error", "threads": []}
    if plat == "tiktok":
        threads = _tiktok_threads(tenant_id=tenant_id, post_id=media_id, limit=limit)
    else:
        threads = await _graph_threads(tenant_id=tenant_id, platform=plat, post_id=media_id, limit=limit)
    return {
        "ok": True,
        "status": "ok" if threads else "empty",
        "threads": threads,
        "platform": plat,
        "post_id": media_id,
    }
