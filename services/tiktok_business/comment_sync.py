"""Incremental TikTok media + comment sync (no comment webhook in Accounts API)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from db.session import whatsapp_session
from services.tiktok_business.config import MAX_COMMENT_PAGES_PER_VIDEO, MAX_VIDEOS_PER_SYNC
from services.tiktok_business.errors import TikTokApiError
from services.tiktok_business.http_client import tiktok_request
from services.tiktok_business.oauth import ensure_fresh_token
from services.tiktok_business.repository import TikTokRepository
from services.tiktok_business.repository_content import TikTokContentRepository
from services.tiktok_business.scopes import comments_read_ready


def _utcnow() -> datetime:
    return datetime.now(UTC)


async def _list_videos(*, access_token: str, open_id: str, cursor: str) -> dict[str, Any]:
    params: dict[str, Any] = {
        "business_id": open_id,
        "fields": '["item_id","caption","thumbnail_url","share_url","create_time"]',
        "max_count": MAX_VIDEOS_PER_SYNC,
    }
    if cursor:
        params["cursor"] = cursor
    return await tiktok_request(method="GET", path="/business/video/list/", access_token=access_token, params=params)


async def _list_comments(*, access_token: str, open_id: str, video_id: str, cursor: str) -> dict[str, Any]:
    params: dict[str, Any] = {
        "business_id": open_id,
        "video_id": video_id,
        "include_replies": "true",
    }
    if cursor:
        params["cursor"] = cursor
    return await tiktok_request(method="GET", path="/business/comment/list/", access_token=access_token, params=params)


def _comment_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    comments = payload.get("comments") or payload.get("comment_list") or payload.get("list") or []
    if not isinstance(comments, list):
        return []
    out: list[dict[str, Any]] = []
    for raw in comments:
        if not isinstance(raw, dict):
            continue
        out.append(raw)
        replies = raw.get("reply_list") or raw.get("replies") or []
        if isinstance(replies, list):
            for reply in replies:
                if isinstance(reply, dict):
                    parent = str(raw.get("comment_id") or raw.get("id") or "")
                    out.append({**reply, "parent_comment_id": reply.get("parent_comment_id") or parent})
    return out


async def sync_connection_comments(*, tenant_id: str, connection_id: str, owner: str = "sync") -> dict[str, Any]:
    new_comments: list[tuple[str, str]] = []
    with whatsapp_session() as session:
        repo = TikTokRepository(session)
        claimed = repo.claim_sync_lease(connection_id, owner=owner)
        if claimed is None:
            return {"skipped": True, "reason": "lease_held"}
        if claimed.tenant_id != tenant_id:
            return {"skipped": True, "reason": "tenant_mismatch"}
        if not comments_read_ready(claimed.granted_scopes):
            claimed.comments_capability = "permission_required"
            session.commit()
            return {"skipped": True, "reason": "missing_comment_scopes"}
        token = await ensure_fresh_token(repo, claimed)
        open_id = claimed.open_id
        cursor = claimed.sync_cursor
        session.commit()

    videos = await _list_videos(access_token=token, open_id=open_id, cursor=cursor)
    video_rows = videos.get("videos") or videos.get("list") or videos.get("video_list") or []
    if not isinstance(video_rows, list):
        video_rows = []
    next_cursor = str(videos.get("cursor") or videos.get("next_cursor") or "")

    with whatsapp_session() as session:
        repo = TikTokRepository(session)
        content = TikTokContentRepository(session)
        connection = repo.get_connection(connection_id, tenant_id=tenant_id)
        if connection is None:
            return {"skipped": True, "reason": "missing_connection"}
        processed_videos = 0
        for raw in video_rows[:MAX_VIDEOS_PER_SYNC]:
            if not isinstance(raw, dict):
                continue
            item_id = str(raw.get("item_id") or raw.get("video_id") or raw.get("id") or "").strip()
            if not item_id:
                continue
            media = content.upsert_media(
                tenant_id=tenant_id,
                connection_id=connection_id,
                item_id=item_id,
                caption=str(raw.get("caption") or raw.get("video_description") or ""),
                thumbnail_url=str(raw.get("thumbnail_url") or raw.get("cover_image_url") or ""),
                share_url=str(raw.get("share_url") or raw.get("embed_url") or ""),
                create_time=raw.get("create_time"),
                status=str(raw.get("status") or ""),
            )
            comment_cursor = media.comment_cursor
            for _page in range(MAX_COMMENT_PAGES_PER_VIDEO):
                try:
                    comments_payload = await _list_comments(
                        access_token=token, open_id=open_id, video_id=item_id, cursor=comment_cursor
                    )
                except TikTokApiError as exc:
                    if exc.retryable:
                        raise
                    break
                for comment in _comment_rows(comments_payload):
                    row, created = content.upsert_comment(
                        tenant_id=tenant_id,
                        connection_id=connection_id,
                        media=media,
                        payload=comment,
                    )
                    if created and not row.is_reply:
                        new_comments.append((row.comment_id, item_id))
                comment_cursor = str(comments_payload.get("cursor") or comments_payload.get("next_cursor") or "")
                has_more = bool(comments_payload.get("has_more") or comments_payload.get("has_more_comments"))
                media.comment_cursor = comment_cursor
                media.last_comment_sync_at = _utcnow()
                if not has_more or not comment_cursor:
                    break
            processed_videos += 1
        connection.last_sync_at = _utcnow()
        connection.sync_cursor = next_cursor
        session.commit()

    for comment_id, item_id in new_comments:
        try:
            from services.job_queue import job_queue

            job_queue.enqueue(
                queue="interactive",
                job_type="tiktok_comment_ai",
                tenant_id=tenant_id,
                payload={"connection_id": connection_id, "comment_id": comment_id, "item_id": item_id},
                idempotency_key=f"tiktok_ai:{tenant_id}:{comment_id}",
            )
        except Exception:
            pass
    return {"ok": True, "videos": processed_videos, "new_comments": len(new_comments)}
