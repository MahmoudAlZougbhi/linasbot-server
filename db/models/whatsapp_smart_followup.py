"""Smart Follow-Up ORM models — durable PG scheduler SoT.

Public product surface: المتابعة الذكية / Smart Follow-Up only.
No campaigns, templates, bulk, or marketing utility reminders.
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


class WhatsAppSmartFollowUpSettings(Base):
    """Tenant-scoped master settings for Smart Follow-Up."""

    __tablename__ = "whatsapp_smart_followup_settings"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_wa_sfu_settings_tenant"),
        CheckConstraint(
            "billing_mode IN ('customer_direct','solution_partner')",
            name="ck_wa_sfu_billing_mode",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    business_hours_only: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    billing_mode: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default=text("'customer_direct'"),
    )
    updated_by_user_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    settings_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    channels_enabled: Mapped[dict[str, Any]] = mapped_column(
        JsonType,
        nullable=False,
        server_default=text(
            '\'{"whatsapp_cloud": true, "instagram_dm": true, "facebook_messenger": true}\''
        ),
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class WhatsAppSmartFollowUpStep(Base):
    """Configured follow-up step (1–3) with absolute delay from trigger AI reply."""

    __tablename__ = "whatsapp_smart_followup_steps"
    __table_args__ = (
        UniqueConstraint("settings_id", "step_index", name="uq_wa_sfu_step_index"),
        CheckConstraint("step_index >= 1 AND step_index <= 3", name="ck_wa_sfu_step_index"),
        CheckConstraint("delay_minutes > 0", name="ck_wa_sfu_delay_positive"),
        CheckConstraint(
            "goal IN ('gentle_check_in','offer_more_help','politely_close')",
            name="ck_wa_sfu_goal",
        ),
        Index("ix_wa_sfu_step_settings", "settings_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    settings_id: Mapped[str] = mapped_column(
        ForeignKey("whatsapp_smart_followup_settings.id"),
        nullable=False,
    )
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    delay_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    goal: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class WhatsAppSmartFollowUpSequence(Base):
    """One follow-up run bound to a conversation epoch after a qualifying AI reply."""

    __tablename__ = "whatsapp_smart_followup_sequences"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "conversation_id",
            "trigger_outbound_intent_id",
            name="uq_wa_sfu_sequence_trigger",
        ),
        CheckConstraint(
            "status IN ('active','completed','cancelled','superseded')",
            name="ck_wa_sfu_sequence_status",
        ),
        Index("ix_wa_sfu_seq_tenant_status", "tenant_id", "status"),
        Index("ix_wa_sfu_seq_conversation", "conversation_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    channel: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'whatsapp_cloud'"))
    connection_id: Mapped[str] = mapped_column(String(36), nullable=False)
    conversation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    trigger_outbound_intent_id: Mapped[str] = mapped_column(String(36), nullable=False)
    channel_context: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False, server_default=text("'{}'"))
    trigger_ai_sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    control_epoch: Mapped[int] = mapped_column(Integer, nullable=False)
    settings_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'active'"))
    cancel_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class WhatsAppSmartFollowUpJob(Base):
    """Durable scheduled job for one step — claimable with exactly-once guards."""

    __tablename__ = "whatsapp_smart_followup_jobs"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_wa_sfu_job_idempotency"),
        UniqueConstraint("sequence_id", "step_index", name="uq_wa_sfu_job_sequence_step"),
        CheckConstraint(
            "status IN ("
            "'scheduled','claimed','generating','sending','sent',"
            "'skipped','cancelled','failed','reconciliation_required'"
            ")",
            name="ck_wa_sfu_job_status",
        ),
        Index("ix_wa_sfu_job_due", "status", "due_at"),
        Index("ix_wa_sfu_job_tenant", "tenant_id", "status"),
        Index("ix_wa_sfu_job_conversation", "conversation_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    channel: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'whatsapp_cloud'"))
    connection_id: Mapped[str] = mapped_column(String(36), nullable=False)
    conversation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    channel_context: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False, server_default=text("'{}'"))
    sequence_id: Mapped[str] = mapped_column(
        ForeignKey("whatsapp_smart_followup_sequences.id"),
        nullable=False,
    )
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    goal: Mapped[str] = mapped_column(String(32), nullable=False)
    delay_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'scheduled'"))
    control_epoch: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claimed_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    reservation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider_wamid: Mapped[str | None] = mapped_column(String(128), nullable=True)
    result_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result_detail: Mapped[str | None] = mapped_column(String(255), nullable=True)
    credits_captured: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WhatsAppSmartFollowUpEvent(Base):
    """Immutable audit / attempt / result events for follow-up jobs."""

    __tablename__ = "whatsapp_smart_followup_events"
    __table_args__ = (
        Index("ix_wa_sfu_event_tenant_created", "tenant_id", "created_at"),
        Index("ix_wa_sfu_event_job", "job_id"),
        Index("ix_wa_sfu_event_sequence", "sequence_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    connection_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    conversation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    sequence_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detail: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False, server_default=text("'{}'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
