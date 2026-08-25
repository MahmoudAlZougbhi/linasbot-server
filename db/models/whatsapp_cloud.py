"""WhatsApp Cloud API + Coexistence ORM models (PostgreSQL SoT).

Tenant-safe bindings, credentials ciphertext, conversation control epochs,
durable webhook/outbound idempotency, and immutable audit events.
"""

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


class WhatsAppConnectionAttempt(Base):
    __tablename__ = "whatsapp_connection_attempts"
    __table_args__ = (
        UniqueConstraint("state_hash", name="uq_wa_attempt_state_hash"),
        CheckConstraint(
            "status IN ('pending','consumed','expired','cancelled','failed','completed')",
            name="ck_wa_attempt_status",
        ),
        CheckConstraint(
            "return_surface IN ('mobile','web','bridge')",
            name="ck_wa_attempt_return_surface",
        ),
        Index("ix_wa_attempt_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    state_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    actor_user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    meta_app_key: Mapped[str] = mapped_column(String(64), nullable=False, server_default=text("'linas_first_party'"))
    return_surface: Mapped[str] = mapped_column(String(16), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    feature_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        server_default=text("'whatsapp_business_app_onboarding'"),
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'pending'"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    outcome_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    outcome_detail: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class WhatsAppConnection(Base):
    __tablename__ = "whatsapp_connections"
    __table_args__ = (
        UniqueConstraint(
            "phone_number_id",
            name="uq_wa_connection_phone_number_id_active",
            # Partial unique for active rows is applied in migration for Postgres;
            # SQLite tests rely on application-level exclusive claim.
        ),
        CheckConstraint(
            "lifecycle_status IN ("
            "'disconnected','starting','awaiting_meta','provisioning','syncing_history',"
            "'connected','needs_attention','failed','revoked'"
            ")",
            name="ck_wa_connection_lifecycle",
        ),
        CheckConstraint(
            "coexistence_mode IN ('whatsapp_business_app_onboarding','api_setup_forbidden')",
            name="ck_wa_connection_coexistence",
        ),
        CheckConstraint(
            "connection_source IN ('embedded_signup','meta_app_review_test')",
            name="ck_wa_connection_source",
        ),
        Index("ix_wa_connection_tenant_lifecycle", "tenant_id", "lifecycle_status"),
        Index("ix_wa_connection_waba", "waba_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_by_user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    meta_app_key: Mapped[str] = mapped_column(String(64), nullable=False, server_default=text("'linas_first_party'"))
    meta_app_id: Mapped[str] = mapped_column(String(32), nullable=False)
    waba_id: Mapped[str] = mapped_column(String(64), nullable=False)
    phone_number_id: Mapped[str] = mapped_column(String(64), nullable=False)
    display_phone_number: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("''"))
    display_phone_last4: Mapped[str] = mapped_column(String(4), nullable=False, server_default=text("''"))
    verified_name: Mapped[str] = mapped_column(String(255), nullable=False, server_default=text("''"))
    coexistence_mode: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        server_default=text("'whatsapp_business_app_onboarding'"),
    )
    connection_source: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        server_default=text("'embedded_signup'"),
    )
    lifecycle_status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'provisioning'"))
    credential_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    credential_generation: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    granted_scopes: Mapped[list[Any]] = mapped_column(JsonType, nullable=False, server_default=text("'[]'"))
    webhook_subscription_status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'unknown'")
    )
    webhook_subscribed_fields: Mapped[list[Any]] = mapped_column(JsonType, nullable=False, server_default=text("'[]'"))
    webhook_last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    health_status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'unknown'"))
    health_detail: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ai_default_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    history_sync_status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'pending'"))
    previous_connection_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    superseded_by_connection_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    revoked_by_user_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class WhatsAppCredential(Base):
    __tablename__ = "whatsapp_credentials"
    __table_args__ = (
        CheckConstraint(
            "token_type IN ('user','system_user','business')",
            name="ck_wa_credential_token_type",
        ),
        Index("ix_wa_credential_tenant", "tenant_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    connection_id: Mapped[str] = mapped_column(
        ForeignKey("whatsapp_connections.id"),
        nullable=False,
        index=True,
    )
    generation: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    encryption_key_version: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'v1'"))
    token_type: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'user'"))
    scopes: Mapped[list[Any]] = mapped_column(JsonType, nullable=False, server_default=text("'[]'"))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class WhatsAppConversation(Base):
    __tablename__ = "whatsapp_conversations"
    __table_args__ = (
        UniqueConstraint(
            "connection_id",
            "customer_wa_id",
            name="uq_wa_conversation_connection_customer",
        ),
        CheckConstraint(
            "control_state IN ('AI_ACTIVE','HUMAN_PAUSED')",
            name="ck_wa_conversation_control_state",
        ),
        Index("ix_wa_conversation_tenant", "tenant_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    connection_id: Mapped[str] = mapped_column(
        ForeignKey("whatsapp_connections.id"),
        nullable=False,
        index=True,
    )
    customer_wa_id: Mapped[str] = mapped_column(String(64), nullable=False)
    customer_profile_name: Mapped[str] = mapped_column(String(255), nullable=False, server_default=text("''"))
    control_state: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'AI_ACTIVE'"))
    control_epoch: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    pause_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_inbound_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_human_outbound_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_ai_outbound_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    service_window_opens_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class WhatsAppMessage(Base):
    __tablename__ = "whatsapp_messages"
    __table_args__ = (
        UniqueConstraint("provider_message_id", name="uq_wa_message_provider_id"),
        CheckConstraint(
            "origin IN ('CUSTOMER','CLOUD_API','BUSINESS_APP','HISTORY','SYSTEM')",
            name="ck_wa_message_origin",
        ),
        CheckConstraint(
            "direction IN ('inbound','outbound')",
            name="ck_wa_message_direction",
        ),
        Index("ix_wa_message_conversation", "conversation_id"),
        Index("ix_wa_message_tenant_created", "tenant_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    connection_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("whatsapp_conversations.id"),
        nullable=False,
    )
    provider_message_id: Mapped[str] = mapped_column(String(128), nullable=False)
    origin: Mapped[str] = mapped_column(String(32), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    message_type: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'text'"))
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'received'"))
    # Retention-controlled: may be empty when retention policy redacts bodies.
    content_redacted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    content_preview: Mapped[str | None] = mapped_column(String(120), nullable=True)
    media_mime: Mapped[str | None] = mapped_column(String(128), nullable=True)
    media_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    meta: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False, server_default=text("'{}'"))
    provider_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WhatsAppOutboundIntent(Base):
    __tablename__ = "whatsapp_outbound_intents"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_wa_outbound_idempotency"),
        CheckConstraint(
            "dispatch_state IN ('pending','sending','sent','failed','suppressed','reconciliation_required')",
            name="ck_wa_outbound_dispatch_state",
        ),
        Index("ix_wa_outbound_conversation", "conversation_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    connection_id: Mapped[str] = mapped_column(String(36), nullable=False)
    conversation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    triggering_inbound_message_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    control_epoch_at_create: Mapped[int] = mapped_column(Integer, nullable=False)
    control_epoch_at_send: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'AI'"))
    dispatch_state: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'pending'"))
    provider_wamid: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(String(255), nullable=True)
    canonical_text: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class WhatsAppWebhookEvent(Base):
    __tablename__ = "whatsapp_webhook_events"
    __table_args__ = (
        UniqueConstraint("event_key", name="uq_wa_webhook_event_key"),
        CheckConstraint(
            "processing_state IN ('claimed','processed','failed','dead_letter','ignored')",
            name="ck_wa_webhook_processing_state",
        ),
        Index("ix_wa_webhook_tenant_created", "tenant_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    connection_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    event_key: Mapped[str] = mapped_column(String(128), nullable=False)
    event_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    processing_state: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'claimed'"))
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    error_detail: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WhatsAppAuditEvent(Base):
    __tablename__ = "whatsapp_audit_events"
    __table_args__ = (Index("ix_wa_audit_tenant_created", "tenant_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    connection_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    conversation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    actor_user_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    detail: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False, server_default=text("'{}'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WhatsAppPilotEntitlement(Base):
    """Audited internal pilot entitlement — never a hardcoded tenant/email bypass."""

    __tablename__ = "whatsapp_pilot_entitlements"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_wa_pilot_tenant"),
        CheckConstraint(
            "status IN ('active','revoked')",
            name="ck_wa_pilot_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'active'"))
    granted_by_user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by_user_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
