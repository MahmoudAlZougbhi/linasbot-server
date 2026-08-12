"""Customer Requests ORM — audit, notes, outbox, idempotency."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
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


class CustomerRequestEvent(Base):
    __tablename__ = "customer_request_events"
    __table_args__ = (
        CheckConstraint(
            "actor_kind IN ('system','ai','operator','customer')",
            name="ck_customer_request_events_actor_kind",
        ),
        Index(
            "ix_customer_request_events_tenant_request_created",
            "tenant_id",
            "request_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    request_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("customer_requests.id"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_user_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    actor_kind: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'system'"))
    payload: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CustomerRequestNote(Base):
    __tablename__ = "customer_request_notes"
    __table_args__ = (
        Index(
            "ix_customer_request_notes_tenant_request_created",
            "tenant_id",
            "request_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    request_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("customer_requests.id"), nullable=False
    )
    author_user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CustomerRequestOutbox(Base):
    __tablename__ = "customer_request_outbox"
    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_customer_request_outbox_idem"),
        CheckConstraint(
            "status IN ('pending','sent','failed','blocked','cancelled')",
            name="ck_customer_request_outbox_status",
        ),
        Index("ix_customer_request_outbox_tenant_request", "tenant_id", "request_id"),
        Index("ix_customer_request_outbox_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    request_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("customer_requests.id"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'pending'"))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    last_error: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CustomerRequestIdempotency(Base):
    __tablename__ = "customer_request_idempotency"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "scope",
            "key",
            name="uq_customer_request_idempotency_scope_key",
        ),
        Index("ix_customer_request_idempotency_tenant_request", "tenant_id", "request_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    scope: Mapped[str] = mapped_column(String(64), nullable=False)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    response_fingerprint: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
