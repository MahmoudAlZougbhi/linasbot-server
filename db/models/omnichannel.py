"""PostgreSQL SoT for omnichannel inbound ledger and outbound outbox."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
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


class OmnichannelInboundEvent(Base):
    __tablename__ = "omnichannel_inbound_events"
    __table_args__ = (
        UniqueConstraint("tenant_id", "channel", "surface", "provider_event_id", name="uq_omni_inbound_provider_event"),
        Index("ix_omni_inbound_tenant_state", "tenant_id", "state"),
        Index("ix_omni_inbound_conversation", "conversation_key"),
        Index("ix_omni_inbound_next_retry", "next_retry_at"),
        CheckConstraint(
            "state IN ('accepted','queued','generating','reply_ready','rate_limited',"
            "'sending','delivered','reconciliation_required','failed','dead_letter')",
            name="ck_omni_inbound_state",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    provider_event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    account_id: Mapped[str] = mapped_column(String(128), nullable=False, server_default=text("''"))
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    surface: Mapped[str] = mapped_column(String(32), nullable=False)
    conversation_key: Mapped[str] = mapped_column(String(255), nullable=False)
    provider_timestamp: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0"))
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'accepted'"))
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    queue_job_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(255), nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False, server_default=text("'{}'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class OmnichannelOutboundOutbox(Base):
    __tablename__ = "omnichannel_outbound_outbox"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_omni_outbound_idempotency"),
        Index("ix_omni_outbound_tenant_state", "tenant_id", "state"),
        Index("ix_omni_outbound_inbound", "inbound_event_id"),
        Index("ix_omni_outbound_next_retry", "next_retry_at"),
        CheckConstraint(
            "state IN ('queued','rate_limited','sending','delivered',"
            "'reconciliation_required','failed','dead_letter','needs_owner_action')",
            name="ck_omni_outbound_state",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    surface: Mapped[str] = mapped_column(String(32), nullable=False)
    account_id: Mapped[str] = mapped_column(String(128), nullable=False, server_default=text("''"))
    conversation_key: Mapped[str] = mapped_column(String(255), nullable=False)
    inbound_event_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    canonical_body: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    idempotency_key: Mapped[str] = mapped_column(String(191), nullable=False)
    control_epoch: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    credit_reservation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    provider_request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    state: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'queued'"))
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_subcode: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'ai'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    regenerated: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
