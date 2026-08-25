"""Handle TikTok comment.update webhooks for comments on any video."""

from __future__ import annotations

import json
from typing import Any

from db.session import whatsapp_session
from services.tiktok_business.comment_sync import enqueue_tiktok_comment_ai, should_enqueue_comment_ai
from services.tiktok_business.errors import TikTokApiError
from services.tiktok_business.http_client import tiktok_request
from services.tiktok_business.oauth import ensure_fresh_token
from services.tiktok_business.repository import TikTokRepository
from services.tiktok_business.repository_content import TikTokContentRepository
from services.tiktok_business.scopes import comments_read_ready

COMMENT_EVENTS = frozenset({"comment.update", "comment.create"})
_SKIP_ACTIONS = frozenset({"delete", "deleted", "hide", "hidden", "remove", "removed"})


def _is_top_level_comment(content: dict[str, Any]) -> bool:
    parent = str(content.get("parent_comment_id") or "").strip()
    if parent and parent not in {"0", "0.0"}:
        return False
    kind = str(content.get("comment_type") or "comment").strip().lower()
    return kind in {"", "comment"}


async def _fetch_public_comment(
    *, access_token: str, open_id: str, video_id: str, comment_id: str
) -> dict[str, Any] | None:
    payload = await tiktok_request(
        method="GET",
        path="/business/comment/list/",
        access_token=access_token,
        params={
            "business_id": open_id,
            "video_id": video_id,
            "comment_ids": json.dumps([comment_id], separators=(",", ":")),
            "status": "PUBLIC",
        },
    )
    rows = payload.get("comments") or payload.get("comment_list") or payload.get("list") or []
    if not isinstance(rows, list) or not rows:
        return None
    raw = rows[0]
    return raw if isinstance(raw, dict) else None


async def handle_comment_webhook(
    *, payload: dict[str, Any], content: dict[str, Any], event_name: str
) -> dict[str, Any]:
    if event_name not in COMMENT_EVENTS:
        return {"accepted": 1, "skipped": True, "reason": "not_comment_insert"}
    action = str(content.get("comment_action") or "").strip().lower()
    if action in _SKIP_ACTIONS:
        return {"accepted": 1, "skipped": True, "reason": "not_insert"}
    if not _is_top_level_comment(content):
        return {"accepted": 1, "skipped": True, "reason": "reply"}
    open_id = str(payload.get("user_openid") or payload.get("open_id") or "").strip()
    comment_id = str(content.get("comment_id") or "").strip()
    video_id = str(content.get("video_id") or content.get("item_id") or "").strip()
    if not open_id or not comment_id or not video_id:
        return {"accepted": 1, "skipped": True, "reason": "missing_ids"}

    with whatsapp_session() as session:
        repo = TikTokRepository(session)
        connection = repo.get_by_open_id_active(open_id)
        if connection is None:
            return {"accepted": 1, "skipped": True, "reason": "missing_connection"}
        if not comments_read_ready(connection.granted_scopes):
            return {"accepted": 1, "skipped": True, "reason": "missing_comment_scopes"}
        token = await ensure_fresh_token(repo, connection)
        tenant_id = connection.tenant_id
        connection_id = connection.id
        connected_at = connection.created_at
        session.commit()

    try:
        comment = await _fetch_public_comment(
            access_token=token, open_id=open_id, video_id=video_id, comment_id=comment_id
        )
    except TikTokApiError as exc:
        if exc.retryable:
            raise
        return {"accepted": 1, "skipped": True, "reason": "comment_fetch_failed"}
    if comment is None:
        return {"accepted": 1, "skipped": True, "reason": "comment_missing"}

    with whatsapp_session() as session:
        content_repo = TikTokContentRepository(session)
        media = content_repo.upsert_media(tenant_id=tenant_id, connection_id=connection_id, item_id=video_id)
        row, created = content_repo.upsert_comment(
            tenant_id=tenant_id,
            connection_id=connection_id,
            media=media,
            payload=comment,
        )
        enqueue = should_enqueue_comment_ai(
            created=created,
            is_reply=row.is_reply,
            payload=comment,
            create_time=row.create_time,
            connected_at=connected_at,
        )
        stored_comment_id = row.comment_id
        session.commit()

    if enqueue:
        enqueue_tiktok_comment_ai(
            tenant_id=tenant_id,
            connection_id=connection_id,
            comment_id=stored_comment_id,
            item_id=video_id,
        )
        return {"accepted": 1, "queued": True}
    return {"accepted": 1, "skipped": True, "reason": "not_new_visitor_comment"}
