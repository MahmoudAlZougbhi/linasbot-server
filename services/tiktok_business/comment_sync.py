"""Catch-up TikTok comment poll for recent videos. All-video coverage is COMMENT webhooks."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from db.session import whatsapp_session
from services.omnichannel.metrics import incr
from services.tiktok_business.config import MAX_COMMENT_PAGES_PER_VIDEO, MAX_VIDEOS_PER_SYNC
from services.tiktok_business.errors import TikTokApiError
from services.tiktok_business.http_client import tiktok_request
from services.tiktok_business.oauth import ensure_fresh_token
from services.tiktok_business.repository import TikTokRepository
from services.tiktok_business.repository_content import TikTokContentRepository
from services.tiktok_business.scopes import comments_read_ready


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def is_video_owner_comment(payload: dict[str, Any]) -> bool:
    return payload.get("owner") is True


def should_enqueue_comment_ai(
    *,
    created: bool,
    is_reply: bool,
    payload: dict[str, Any],
    create_time: datetime | None,
    connected_at: datetime | None,
) -> bool:
    if not created or is_reply or is_video_owner_comment(payload):
        return False
    comment_at = _aware(create_time)
    connected = _aware(connected_at)
    if comment_at is None or connected is None:
        return False
    return comment_at >= connected


def persist_comment_page_cursor(
    *, page_number: int, page_limit: int, has_more: bool, cursor: str
) -> tuple[str, bool]:
    """Return (cursor_to_store, truncated). Empty cursor means this video is complete."""
    token = str(cursor or "").strip()
    if not has_more or not token:
        return "", False
    if int(page_number) >= int(page_limit):
        return token, True
    return token, False


def enqueue_tiktok_comment_ai(*, tenant_id: str, connection_id: str, comment_id: str, item_id: str) -> None:
    from services.job_queue import job_queue
    from services.omnichannel.queues import physical_queue_for

    job_queue.enqueue(
        queue=physical_queue_for("comments"),  # type: ignore[arg-type]
        job_type="tiktok_comment_ai",
        tenant_id=tenant_id,
        payload={
            "connection_id": connection_id,
            "comment_id": comment_id,
            "item_id": item_id,
            "_conversation_key": f"{tenant_id}:tiktok:{comment_id}",
        },
        idempotency_key=f"tiktok_ai:{tenant_id}:{comment_id}",
    )


async def _list_videos(*, access_token: str, open_id: str) -> dict[str, Any]:
    params: dict[str, Any] = {
        "business_id": open_id,
        "fields": '["item_id","caption","thumbnail_url","share_url","create_time"]',
        "max_count": MAX_VIDEOS_PER_SYNC,
    }
    return await tiktok_request(method="GET", path="/business/video/list/", access_token=access_token, params=params)


async def _list_comments(*, access_token: str, open_id: str, video_id: str, cursor: str) -> dict[str, Any]:
    params: dict[str, Any] = {
        "business_id": open_id,
        "video_id": video_id,
        "include_replies": "false",
        "status": "PUBLIC",
        "sort_field": "create_time",
        "sort_order": "desc",
        "max_count": 30,
    }
    if cursor:
        params["cursor"] = cursor
    return await tiktok_request(method="GET", path="/business/comment/list/", access_token=access_token, params=params)


def _comment_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    comments = payload.get("comments") or payload.get("comment_list") or payload.get("list") or []
    if not isinstance(comments, list):
        return []
    return [raw for raw in comments if isinstance(raw, dict)]


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
        session.commit()

    videos = await _list_videos(access_token=token, open_id=open_id)
    video_rows = videos.get("videos") or videos.get("list") or videos.get("video_list") or []
    if not isinstance(video_rows, list):
        video_rows = []

    with whatsapp_session() as session:
        repo = TikTokRepository(session)
        content = TikTokContentRepository(session)
        connection = repo.get_connection(connection_id, tenant_id=tenant_id)
        if connection is None:
            return {"skipped": True, "reason": "missing_connection"}
        connected_at = connection.created_at
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
            comment_cursor = str(getattr(media, "comment_cursor", "") or "")
            for page_number in range(1, MAX_COMMENT_PAGES_PER_VIDEO + 1):
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
                    if should_enqueue_comment_ai(
                        created=created,
                        is_reply=row.is_reply,
                        payload=comment,
                        create_time=row.create_time,
                        connected_at=connected_at,
                    ):
                        new_comments.append((row.comment_id, item_id))
                comment_cursor = str(comments_payload.get("cursor") or comments_payload.get("next_cursor") or "")
                has_more = bool(comments_payload.get("has_more") or comments_payload.get("has_more_comments"))
                stored, truncated = persist_comment_page_cursor(
                    page_number=page_number,
                    page_limit=MAX_COMMENT_PAGES_PER_VIDEO,
                    has_more=has_more,
                    cursor=comment_cursor,
                )
                media.comment_cursor = stored
                media.last_comment_sync_at = _utcnow()
                if truncated:
                    incr("tiktok_comment_pagination_truncated")
                    break
                if not stored:
                    break
            processed_videos += 1
        connection.last_sync_at = _utcnow()
        connection.sync_cursor = ""
        session.commit()

    for comment_id, item_id in new_comments:
        enqueue_tiktok_comment_ai(
            tenant_id=tenant_id, connection_id=connection_id, comment_id=comment_id, item_id=item_id
        )
    return {"ok": True, "videos": processed_videos, "new_comments": len(new_comments)}
