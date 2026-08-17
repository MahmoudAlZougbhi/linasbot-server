"""TikTok media, comments, replies, conversations, messages — tenant isolated."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import (
    text as sql_text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from db.models.base import Base

JsonType = JSON().with_variant(JSONB(), "postgresql")


def _uuid() -> str:
    return str(uuid.uuid4())


class TikTokMedia(Base):
    __tablename__ = "tiktok_media"
    __table_args__ = (
        UniqueConstraint("tenant_id", "item_id", name="uq_tt_media_tenant_item"),
        Index("ix_tt_media_connection", "connection_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    connection_id: Mapped[str] = mapped_column(ForeignKey("tiktok_connections.id"), nullable=False)
    item_id: Mapped[str] = mapped_column(String(64), nullable=False)
    caption: Mapped[str] = mapped_column(Text, nullable=False, server_default=sql_text("''"))
    thumbnail_url: Mapped[str] = mapped_column(String(1024), nullable=False, server_default=sql_text("''"))
    share_url: Mapped[str] = mapped_column(String(1024), nullable=False, server_default=sql_text("''"))
    create_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=sql_text("''"))
    last_comment_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    comment_cursor: Mapped[str] = mapped_column(String(128), nullable=False, server_default=sql_text("''"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TikTokComment(Base):
    __tablename__ = "tiktok_comments"
    __table_args__ = (
        UniqueConstraint("tenant_id", "comment_id", name="uq_tt_comment_tenant_id"),
        CheckConstraint(
            "status IN ('public','hidden','deleted','unknown')",
            name="ck_tt_comment_status",
        ),
        Index("ix_tt_comment_connection_created", "connection_id", "create_time"),
        Index("ix_tt_comment_media", "media_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    connection_id: Mapped[str] = mapped_column(ForeignKey("tiktok_connections.id"), nullable=False)
    media_id: Mapped[str] = mapped_column(ForeignKey("tiktok_media.id"), nullable=False)
    comment_id: Mapped[str] = mapped_column(String(64), nullable=False)
    parent_comment_id: Mapped[str] = mapped_column(String(64), nullable=False, server_default=sql_text("''"))
    video_item_id: Mapped[str] = mapped_column(String(64), nullable=False)
    author_user_id: Mapped[str] = mapped_column(String(128), nullable=False, server_default=sql_text("''"))
    author_username: Mapped[str] = mapped_column(String(255), nullable=False, server_default=sql_text("''"))
    author_avatar_url: Mapped[str] = mapped_column(String(1024), nullable=False, server_default=sql_text("''"))
    text: Mapped[str] = mapped_column(Text, nullable=False, server_default=sql_text("''"))
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=sql_text("'public'"))
    create_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_reply: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sql_text("false"))
    ai_processed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sql_text("false"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TikTokCommentReply(Base):
    __tablename__ = "tiktok_comment_replies"
    __table_args__ = (
        UniqueConstraint("tenant_id", "comment_id", name="uq_tt_reply_tenant_comment"),
        CheckConstraint(
            "delivery_status IN ('pending','sending','sent','failed','skipped','retrying')",
            name="ck_tt_reply_delivery",
        ),
        Index("ix_tt_reply_status", "delivery_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    connection_id: Mapped[str] = mapped_column(ForeignKey("tiktok_connections.id"), nullable=False)
    comment_id: Mapped[str] = mapped_column(String(64), nullable=False)
    reply_text: Mapped[str] = mapped_column(Text, nullable=False, server_default=sql_text("''"))
    delivery_status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=sql_text("'pending'"))
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=sql_text("0"))
    tiktok_request_id: Mapped[str] = mapped_column(String(128), nullable=False, server_default=sql_text("''"))
    tiktok_reply_id: Mapped[str] = mapped_column(String(64), nullable=False, server_default=sql_text("''"))
    last_error: Mapped[str] = mapped_column(String(255), nullable=False, server_default=sql_text("''"))
    model: Mapped[str] = mapped_column(String(64), nullable=False, server_default=sql_text("''"))
    tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default=sql_text("0"))
    cost_usd: Mapped[str] = mapped_column(String(32), nullable=False, server_default=sql_text("''"))
    credits_used: Mapped[int] = mapped_column(Integer, nullable=False, server_default=sql_text("0"))
    automation_on: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sql_text("false"))
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TikTokConversation(Base):
    __tablename__ = "tiktok_conversations"
    __table_args__ = (
        UniqueConstraint("connection_id", "conversation_id", name="uq_tt_conv_connection_cid"),
        Index("ix_tt_conv_tenant", "tenant_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    connection_id: Mapped[str] = mapped_column(ForeignKey("tiktok_connections.id"), nullable=False)
    conversation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    customer_open_id: Mapped[str] = mapped_column(String(128), nullable=False)
    customer_username: Mapped[str] = mapped_column(String(255), nullable=False, server_default=sql_text("''"))
    customer_avatar_url: Mapped[str] = mapped_column(String(1024), nullable=False, server_default=sql_text("''"))
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_message_preview: Mapped[str] = mapped_column(String(255), nullable=False, server_default=sql_text("''"))
    unread_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=sql_text("0"))
    ai_status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=sql_text("'idle'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TikTokMessage(Base):
    __tablename__ = "tiktok_messages"
    __table_args__ = (
        UniqueConstraint("tenant_id", "provider_message_id", name="uq_tt_msg_tenant_provider"),
        Index("ix_tt_msg_conversation", "conversation_row_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    connection_id: Mapped[str] = mapped_column(ForeignKey("tiktok_connections.id"), nullable=False)
    conversation_row_id: Mapped[str] = mapped_column(ForeignKey("tiktok_conversations.id"), nullable=False)
    provider_message_id: Mapped[str] = mapped_column(String(128), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False, server_default=sql_text("''"))
    message_type: Mapped[str] = mapped_column(String(32), nullable=False, server_default=sql_text("'text'"))
    delivery_status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=sql_text("'received'"))
    tiktok_request_id: Mapped[str] = mapped_column(String(128), nullable=False, server_default=sql_text("''"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
