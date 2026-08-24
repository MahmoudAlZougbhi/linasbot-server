"""Persist TikTok media, comments, replies, conversations — idempotent inserts."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from db.models.tiktok_business import TikTokWebhookEvent
from db.models.tiktok_content import (
    TikTokComment,
    TikTokCommentReply,
    TikTokConversation,
    TikTokMedia,
    TikTokMessage,
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _epoch(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return None
    if seconds > 1e12:
        seconds /= 1000.0
    return datetime.fromtimestamp(seconds, tz=UTC)


class TikTokContentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert_media(
        self,
        *,
        tenant_id: str,
        connection_id: str,
        item_id: str,
        caption: str = "",
        thumbnail_url: str = "",
        share_url: str = "",
        create_time: Any = None,
        status: str = "",
    ) -> TikTokMedia:
        row = self.session.scalar(
            select(TikTokMedia).where(TikTokMedia.tenant_id == tenant_id, TikTokMedia.item_id == item_id)
        )
        if row is None:
            row = TikTokMedia(
                id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                connection_id=connection_id,
                item_id=item_id,
            )
            self.session.add(row)
        row.caption = (caption or "")[:8000]
        row.thumbnail_url = (thumbnail_url or "")[:1024]
        row.share_url = (share_url or "")[:1024]
        row.create_time = _epoch(create_time)
        row.status = (status or "")[:32]
        self.session.flush()
        return row

    def list_media(self, *, tenant_id: str, connection_id: str, limit: int = 25, after: str = "") -> list[TikTokMedia]:
        stmt = (
            select(TikTokMedia)
            .where(TikTokMedia.tenant_id == tenant_id, TikTokMedia.connection_id == connection_id)
            .order_by(TikTokMedia.create_time.desc())
            .limit(limit)
        )
        rows = list(self.session.scalars(stmt))
        if after:
            rows = [row for row in rows if row.item_id < after][:limit]
        return rows

    def upsert_comment(
        self,
        *,
        tenant_id: str,
        connection_id: str,
        media: TikTokMedia,
        payload: dict[str, Any],
    ) -> tuple[TikTokComment, bool]:
        comment_id = str(payload.get("comment_id") or payload.get("id") or "").strip()
        if not comment_id:
            raise ValueError("comment_id required")
        existing = self.session.scalar(
            select(TikTokComment).where(TikTokComment.tenant_id == tenant_id, TikTokComment.comment_id == comment_id)
        )
        created = existing is None
        row = existing or TikTokComment(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            connection_id=connection_id,
            media_id=media.id,
            comment_id=comment_id,
            video_item_id=media.item_id,
        )
        if created:
            self.session.add(row)
        raw_user = payload.get("user")
        user: dict[str, Any] = raw_user if isinstance(raw_user, dict) else {}
        row.parent_comment_id = str(payload.get("parent_comment_id") or "")[:64]
        row.author_user_id = str(
            payload.get("unique_identifier")
            or user.get("unique_identifier")
            or payload.get("user_id")
            or user.get("open_id")
            or ""
        )[:128]
        row.author_username = str(
            payload.get("username")
            or payload.get("display_name")
            or user.get("username")
            or user.get("display_name")
            or ""
        )[:255]
        row.author_avatar_url = str(payload.get("profile_image") or user.get("profile_image") or "")[:1024]
        row.text = str(payload.get("text") or payload.get("comment") or "")[:8000]
        status = str(payload.get("status") or "PUBLIC").strip().lower()
        row.status = status if status in {"public", "hidden", "deleted"} else "unknown"
        row.create_time = _epoch(payload.get("create_time"))
        row.is_reply = bool(row.parent_comment_id)
        self.session.flush()
        return row, created

    def claim_comment_for_ai(self, *, tenant_id: str, comment_id: str) -> TikTokComment | None:
        stmt = (
            update(TikTokComment)
            .where(
                TikTokComment.tenant_id == tenant_id,
                TikTokComment.comment_id == comment_id,
                TikTokComment.ai_processed.is_(False),
                TikTokComment.is_reply.is_(False),
            )
            .values(ai_processed=True)
        )
        result = self.session.execute(stmt)
        if int(result.rowcount or 0) != 1:
            return None
        return self.session.scalar(
            select(TikTokComment).where(TikTokComment.tenant_id == tenant_id, TikTokComment.comment_id == comment_id)
        )

    def get_or_create_reply_job(
        self, *, tenant_id: str, connection_id: str, comment_id: str
    ) -> tuple[TikTokCommentReply, bool]:
        existing = self.session.scalar(
            select(TikTokCommentReply).where(
                TikTokCommentReply.tenant_id == tenant_id, TikTokCommentReply.comment_id == comment_id
            )
        )
        if existing is not None:
            return existing, False
        row = TikTokCommentReply(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            connection_id=connection_id,
            comment_id=comment_id,
            delivery_status="pending",
        )
        self.session.add(row)
        self.session.flush()
        return row, True

    def list_comments_inbox(
        self, *, tenant_id: str, limit: int = 50, connection_id: str | None = None
    ) -> list[dict[str, Any]]:
        stmt = (
            select(TikTokComment, TikTokMedia, TikTokCommentReply)
            .join(TikTokMedia, TikTokMedia.id == TikTokComment.media_id)
            .outerjoin(
                TikTokCommentReply,
                (TikTokCommentReply.tenant_id == TikTokComment.tenant_id)
                & (TikTokCommentReply.comment_id == TikTokComment.comment_id),
            )
            .where(TikTokComment.tenant_id == tenant_id)
            .order_by(TikTokComment.create_time.desc())
            .limit(limit)
        )
        if connection_id:
            stmt = stmt.where(TikTokComment.connection_id == connection_id)
        rows: list[dict[str, Any]] = []
        for comment, media, reply in self.session.execute(stmt):
            rows.append(
                {
                    "platform": "tiktok",
                    "comment_id": comment.comment_id,
                    "parent_comment_id": comment.parent_comment_id,
                    "text": comment.text,
                    "status": comment.status,
                    "create_time": comment.create_time.isoformat() if comment.create_time else None,
                    "author_username": comment.author_username,
                    "author_avatar_url": comment.author_avatar_url,
                    "post_preview": media.caption,
                    "post_thumbnail": media.thumbnail_url,
                    "post_id": media.item_id,
                    "permalink": media.share_url,
                    "ai_reply": reply.reply_text if reply else "",
                    "delivery_status": reply.delivery_status if reply else "none",
                    "delivery_error": reply.last_error if reply else "",
                    "automation": bool(reply.automation_on) if reply else False,
                }
            )
        return rows

    def claim_webhook_event(self, *, event_id: str, event_name: str, tenant_id: str = "") -> bool:
        existing = self.session.scalar(select(TikTokWebhookEvent).where(TikTokWebhookEvent.event_id == event_id))
        if existing is not None:
            return False
        self.session.add(
            TikTokWebhookEvent(
                id=str(uuid.uuid4()),
                event_id=event_id,
                tenant_id=tenant_id,
                event_name=event_name,
                processed=True,
            )
        )
        try:
            self.session.flush()
        except IntegrityError:
            self.session.rollback()
            return False
        return True

    def upsert_conversation(
        self,
        *,
        tenant_id: str,
        connection_id: str,
        conversation_id: str,
        customer_open_id: str,
        username: str = "",
        avatar_url: str = "",
        preview: str = "",
        at: datetime | None = None,
        increment_unread: bool = False,
    ) -> TikTokConversation:
        row = self.session.scalar(
            select(TikTokConversation).where(
                TikTokConversation.connection_id == connection_id,
                TikTokConversation.conversation_id == conversation_id,
            )
        )
        if row is None:
            row = TikTokConversation(
                id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                connection_id=connection_id,
                conversation_id=conversation_id,
                customer_open_id=customer_open_id,
            )
            self.session.add(row)
        row.customer_username = (username or row.customer_username or "")[:255]
        row.customer_avatar_url = (avatar_url or row.customer_avatar_url or "")[:1024]
        row.last_message_preview = (preview or "")[:255]
        row.last_message_at = at or _utcnow()
        if increment_unread:
            row.unread_count = int(row.unread_count or 0) + 1
        self.session.flush()
        return row

    def insert_message(
        self,
        *,
        tenant_id: str,
        connection_id: str,
        conversation_row_id: str,
        provider_message_id: str,
        direction: str,
        text: str,
        message_type: str = "text",
        delivery_status: str = "received",
        tiktok_request_id: str = "",
    ) -> tuple[TikTokMessage, bool]:
        existing = self.session.scalar(
            select(TikTokMessage).where(
                TikTokMessage.tenant_id == tenant_id,
                TikTokMessage.provider_message_id == provider_message_id,
            )
        )
        if existing is not None:
            return existing, False
        row = TikTokMessage(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            connection_id=connection_id,
            conversation_row_id=conversation_row_id,
            provider_message_id=provider_message_id,
            direction=direction,
            text=(text or "")[:8000],
            message_type=message_type[:32],
            delivery_status=delivery_status[:16],
            tiktok_request_id=tiktok_request_id[:128],
        )
        self.session.add(row)
        self.session.flush()
        return row, True
