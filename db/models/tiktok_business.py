"""TikTok Business ORM: OAuth attempts, connections, credentials, audit."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
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


class TikTokOAuthAttempt(Base):
    __tablename__ = "tiktok_oauth_attempts"
    __table_args__ = (
        UniqueConstraint("state_hash", name="uq_tt_oauth_state_hash"),
        CheckConstraint(
            "status IN ('pending','consumed','expired','cancelled','failed')",
            name="ck_tt_oauth_status",
        ),
        CheckConstraint("return_surface IN ('mobile','web')", name="ck_tt_oauth_surface"),
        Index("ix_tt_oauth_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    state_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    actor_user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    return_surface: Mapped[str] = mapped_column(String(16), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'pending'"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    outcome_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TikTokConnection(Base):
    __tablename__ = "tiktok_connections"
    __table_args__ = (
        CheckConstraint(
            "lifecycle_status IN ("
            "'disconnected','connecting','connected','permission_required',"
            "'token_expired','error','revoked'"
            ")",
            name="ck_tt_connection_lifecycle",
        ),
        Index("ix_tt_connection_tenant_life", "tenant_id", "lifecycle_status"),
        Index("ix_tt_connection_open_id", "open_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_by_user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    authorized_by_user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    open_id: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False, server_default=text("''"))
    username: Mapped[str] = mapped_column(String(255), nullable=False, server_default=text("''"))
    avatar_url: Mapped[str] = mapped_column(String(1024), nullable=False, server_default=text("''"))
    granted_scopes: Mapped[list[Any]] = mapped_column(JsonType, nullable=False, server_default=text("'[]'"))
    lifecycle_status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'connecting'"))
    credential_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(255), nullable=True)
    comments_capability: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'disconnected'"))
    dm_capability: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'permission_pending'"))
    webhook_status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'unregistered'"))
    sync_lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sync_lease_owner: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sync_cursor: Mapped[str] = mapped_column(String(128), nullable=False, server_default=text("''"))
    previous_connection_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    superseded_by_connection_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by_user_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TikTokCredential(Base):
    __tablename__ = "tiktok_credentials"
    __table_args__ = (Index("ix_tt_credential_tenant", "tenant_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    connection_id: Mapped[str] = mapped_column(ForeignKey("tiktok_connections.id"), nullable=False, index=True)
    ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    scopes: Mapped[list[Any]] = mapped_column(JsonType, nullable=False, server_default=text("'[]'"))
    access_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    refresh_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TikTokAuditEvent(Base):
    __tablename__ = "tiktok_audit_events"
    __table_args__ = (Index("ix_tt_audit_tenant_created", "tenant_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    connection_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    actor_user_id: Mapped[str] = mapped_column(String(128), nullable=False, server_default=text("''"))
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    detail: Mapped[str] = mapped_column(String(255), nullable=False, server_default=text("''"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TikTokWebhookEvent(Base):
    __tablename__ = "tiktok_webhook_events"
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_tt_webhook_event_id"),
        Index("ix_tt_webhook_tenant", "tenant_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, server_default=text("''"))
    connection_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    event_name: Mapped[str] = mapped_column(String(64), nullable=False)
    processed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    tiktok_request_id: Mapped[str] = mapped_column(String(128), nullable=False, server_default=text("''"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
