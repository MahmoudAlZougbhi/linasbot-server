"""Build the operator post grid for Instagram, Facebook, and TikTok."""

from __future__ import annotations

from typing import Any

from services.comments_inbox.kinds import media_kind
from services.comments_inbox.watchlist import platform_watch
from services.customer_reply_v2.connected_posts import list_connected_posts, list_tenant_comment_accounts


def _account_for(tenant_id: str, platform: str) -> dict[str, str] | None:
    plat = str(platform or "").strip().lower()
    for row in list_tenant_comment_accounts(tenant_id):
        if row.get("platform") == plat:
            return row
    return None


def _tiktok_comment_counts(tenant_id: str, item_ids: list[str]) -> dict[str, int]:
    if not item_ids:
        return {}
    try:
        from sqlalchemy import func, select

        from db.models.tiktok_content import TikTokComment
        from db.session import whatsapp_db_configured, whatsapp_session
    except Exception:
        return {}
    if not whatsapp_db_configured():
        return {}
    with whatsapp_session() as session:
        stmt = (
            select(TikTokComment.video_item_id, func.count())
            .where(
                TikTokComment.tenant_id == tenant_id,
                TikTokComment.video_item_id.in_(item_ids),
                TikTokComment.is_reply.is_(False),
            )
            .group_by(TikTokComment.video_item_id)
        )
        return {str(item_id): int(count or 0) for item_id, count in session.execute(stmt)}


def _decorate(posts: list[dict[str, Any]], *, platform: str, watch: dict[str, Any]) -> list[dict[str, Any]]:
    selected_mode = str(watch.get("mode") or "all") == "selected"
    watched = {str(item) for item in (watch.get("post_ids") or [])}
    out: list[dict[str, Any]] = []
    for raw in posts:
        post_id = str(raw.get("id") or "").strip()
        if not post_id:
            continue
        kind = media_kind(str(raw.get("media_type") or ""), platform=platform)
        try:
            count = int(raw.get("comment_count") or 0)
        except (TypeError, ValueError):
            count = 0
        out.append(
            {
                "id": post_id,
                "caption": str(raw.get("preview") or raw.get("caption") or ""),
                "created_time": str(raw.get("created_time") or ""),
                "permalink": str(raw.get("permalink") or ""),
                "thumbnail": str(raw.get("thumbnail") or ""),
                "media_type": str(raw.get("media_type") or ""),
                "kind": kind,
                "comment_count": count,
                "watched": True if not selected_mode else post_id in watched,
            }
        )
    return out


async def list_comment_media(
    *,
    tenant_id: str,
    platform: str,
    after: str = "",
    limit: int = 24,
) -> dict[str, Any]:
    plat = str(platform or "").strip().lower()
    account = _account_for(tenant_id, plat)
    watch = platform_watch(tenant_id, plat)
    if account is None:
        return {
            "ok": False,
            "status": "disconnected",
            "platform": plat,
            "account_name": "",
            "posts": [],
            "next_after": "",
            "watch": watch,
        }
    result = await list_connected_posts(
        tenant_id=tenant_id,
        platform=plat,
        connected_account_id=account["connected_account_id"],
        after=after,
        limit=limit,
    )
    posts = list(result.get("posts") or [])
    if plat == "tiktok":
        counts = _tiktok_comment_counts(tenant_id, [str(row.get("id") or "") for row in posts])
        for row in posts:
            row["comment_count"] = counts.get(str(row.get("id") or ""), 0)
    decorated = _decorate(posts, platform=plat, watch=watch)
    status = "ok" if result.get("ok") else "error"
    if result.get("ok") and not decorated and not after:
        status = "empty"
    return {
        "ok": bool(result.get("ok")),
        "status": status,
        "error": str(result.get("error") or ""),
        "platform": plat,
        "account_name": account.get("name") or "",
        "account_id": account.get("connected_account_id") or "",
        "posts": decorated,
        "next_after": str(result.get("next_after") or ""),
        "watch": watch,
    }
