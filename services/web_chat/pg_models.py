"""PostgreSQL SoT models for Website Chat visitor sessions and delivery."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from db.models.base import Base

JsonType = JSON()


def _uuid() -> str:
    return str(uuid.uuid4())


class WebChatVisitorSessionRow(Base):
    __tablename__ = "web_chat_visitor_sessions"
    __table_args__ = (
        UniqueConstraint("session_id", name="uq_web_chat_visitor_sessions_session_id"),
        Index("ix_web_chat_visitor_sessions_tenant_widget", "tenant_id", "widget_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(String(80), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    widget_key: Mapped[str] = mapped_column(String(120), nullable=False)
    authority_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class WebChatMessageRow(Base):
    __tablename__ = "web_chat_messages"
    __table_args__ = (
        UniqueConstraint("session_id", "message_id", name="uq_web_chat_messages_session_message"),
        Index("ix_web_chat_messages_session_created", "session_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(String(80), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    message_id: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    acked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    meta: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)


class WebChatDeliveryIdempotencyRow(Base):
    __tablename__ = "web_chat_delivery_idempotency"
    __table_args__ = (UniqueConstraint("tenant_id", "idempotency_key", name="uq_web_chat_delivery_idempotency"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    session_id: Mapped[str] = mapped_column(String(80), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    message_id: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WebChatWidgetRow(Base):
    __tablename__ = "web_chat_widgets"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_web_chat_widgets_tenant_id"),
        UniqueConstraint("widget_key", name="uq_web_chat_widgets_widget_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    widget_key: Mapped[str] = mapped_column(String(120), nullable=False)
    config: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


WEB_CHAT_HA_TABLES: tuple[str, ...] = (
    "web_chat_visitor_sessions",
    "web_chat_messages",
    "web_chat_delivery_idempotency",
    "web_chat_widgets",
    "web_chat_operations",
)


class WebChatOperationRow(Base):
    __tablename__ = "web_chat_operations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "operation_key", name="uq_web_chat_operations_tenant_key"),
        Index("ix_web_chat_operations_state", "state"),
        Index("ix_web_chat_operations_session", "session_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    session_id: Mapped[str] = mapped_column(String(80), nullable=False)
    operation_key: Mapped[str] = mapped_column(String(200), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    attempt: Mapped[int] = mapped_column(nullable=False, default=1)
    lease_owner: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    lease_generation: Mapped[int] = mapped_column(nullable=False, default=1)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reservation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    released: Mapped[bool] = mapped_column(nullable=False, default=False)
    result: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    snapshot: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
