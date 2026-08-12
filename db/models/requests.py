"""Customer Requests ORM — core request rows (PostgreSQL SoT)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from db.models.base import Base

JsonType = JSON().with_variant(JSONB(), "postgresql")


def _uuid() -> str:
    return str(uuid.uuid4())


class CustomerRequest(Base):
    __tablename__ = "customer_requests"
    __table_args__ = (
        UniqueConstraint("tenant_id", "request_number", name="uq_customer_requests_tenant_number"),
        CheckConstraint(
            "request_type IN ('ORDER','APPOINTMENT','OTHER')",
            name="ck_customer_requests_type",
        ),
        CheckConstraint(
            "status IN ("
            "'NEW','IN_REVIEW','WAITING_FOR_CUSTOMER',"
            "'CONFIRMED','READY','COMPLETED','CANCELLED')",
            name="ck_customer_requests_status",
        ),
        CheckConstraint(
            "source_channel IN ("
            "'instagram_dm','facebook_messenger',"
            "'whatsapp_cloud','comment_linked_dm')",
            name="ck_customer_requests_channel",
        ),
        CheckConstraint(
            "notification_status IN ('none','pending','sent','failed','blocked')",
            name="ck_customer_requests_notification_status",
        ),
        Index("ix_customer_requests_tenant_status_created", "tenant_id", "status", "created_at"),
        Index("ix_customer_requests_tenant_type_created", "tenant_id", "request_type", "created_at"),
        Index(
            "ix_customer_requests_tenant_assignee_created",
            "tenant_id",
            "assigned_user_id",
            "created_at",
        ),
        Index(
            "ix_customer_requests_tenant_channel_created",
            "tenant_id",
            "source_channel",
            "created_at",
        ),
        Index("ix_customer_requests_tenant_phone", "tenant_id", "phone_normalized"),
        Index("ix_customer_requests_tenant_conversation", "tenant_id", "conversation_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    request_number: Mapped[str] = mapped_column(String(32), nullable=False)
    request_type: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'NEW'"))
    source_channel: Mapped[str] = mapped_column(String(32), nullable=False)
    source_account_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    external_customer_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    platform_username: Mapped[str | None] = mapped_column(String(256), nullable=True)
    customer_display_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    customer_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    phone_normalized: Mapped[str | None] = mapped_column(String(32), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    conversation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    originating_message_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    originating_comment_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    collected_fields: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    requested_items: Mapped[list[Any] | dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    requested_branch: Mapped[str | None] = mapped_column(String(256), nullable=True)
    preferred_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    preferred_time: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fulfillment_preference: Mapped[str | None] = mapped_column(String(32), nullable=True)
    delivery_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    assigned_user_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    configuration_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    notification_status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'none'")
    )
    last_notification_error: Mapped[str | None] = mapped_column(String(512), nullable=True)
    completion_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    manual_mode_conversation_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CustomerRequestCounter(Base):
    """Per-tenant sequence for human-readable request numbers."""

    __tablename__ = "customer_request_counters"

    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    next_number: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
