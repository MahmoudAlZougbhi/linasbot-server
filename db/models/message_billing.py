"""Message ledger, daily AI Setup edits, and internal expense journal ORM.

Matches alembic revision 20260910_msg_billing. Live credit tables are unchanged.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Index, Integer, Numeric, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from db.models.base import Base

JsonType = JSON().with_variant(JSONB(), "postgresql")


class CustomerAiMessageLotRow(Base):
    __tablename__ = "customer_ai_message_lots"
    __table_args__ = (Index("ix_message_lots_tenant", "tenant_id"),)

    lot_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    period_id: Mapped[str] = mapped_column(String(64), nullable=False)
    granted: Mapped[int] = mapped_column(Integer, nullable=False)
    remaining: Mapped[int] = mapped_column(Integer, nullable=False)
    expires: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    catalog_version: Mapped[str] = mapped_column(String(64), nullable=False, server_default=text("''"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class CustomerAiMessageReservationRow(Base):
    __tablename__ = "customer_ai_message_reservations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "operation_id", name="uq_message_reservation_op"),
        Index("ix_message_reservations_status_created", "status", "created_at"),
    )

    reservation_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    operation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    units: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    lot_id: Mapped[str] = mapped_column(String(64), nullable=False, server_default=text("''"))
    period_id: Mapped[str] = mapped_column(String(64), nullable=False, server_default=text("''"))
    response_class: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("''"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class CustomerAiDailyEditRow(Base):
    __tablename__ = "customer_ai_daily_edits"
    __table_args__ = (
        UniqueConstraint("tenant_id", "window_id", "operation_id", name="uq_daily_edit_op"),
        Index("ix_daily_edits_tenant_window", "tenant_id", "window_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    window_id: Mapped[str] = mapped_column(String(16), nullable=False)
    operation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class CustomerAiDailyEditPolicyRow(Base):
    __tablename__ = "customer_ai_daily_edit_policies"

    tenant_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    limit_value: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'tenant_override'"))
    actor: Mapped[str] = mapped_column(String(128), nullable=False, server_default=text("''"))
    reason: Mapped[str] = mapped_column(String(255), nullable=False, server_default=text("''"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class CustomerAiExpenseEventRow(Base):
    __tablename__ = "customer_ai_expense_events"
    __table_args__ = (Index("ix_expense_events_tenant", "tenant_id"),)

    event_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    feature: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False, server_default=text("''"))
    amount_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(16, 6), nullable=False, server_default=text("1"))
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    environment: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'test'"))
    operation_id: Mapped[str] = mapped_column(String(128), nullable=False, server_default=text("''"))
    parent_event_id: Mapped[str] = mapped_column(String(128), nullable=False, server_default=text("''"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    extra: Mapped[dict | None] = mapped_column(JsonType, nullable=True)


class CustomerAiPendingSettlementRow(Base):
    __tablename__ = "customer_ai_pending_settlements"
    __table_args__ = (Index("ix_pending_settlements_state_id", "state", "settlement_id"),)

    settlement_id: Mapped[str] = mapped_column(String(220), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    reservation_id: Mapped[str] = mapped_column(String(160), nullable=False, server_default=text("''"))
    operation_id: Mapped[str] = mapped_column(String(160), nullable=False, server_default=text("''"))
    billing_policy: Mapped[str] = mapped_column(String(32), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(64), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    send_status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("''"))
    provider_message_id: Mapped[str] = mapped_column(String(160), nullable=False, server_default=text("''"))
    channel: Mapped[str] = mapped_column(String(64), nullable=False, server_default=text("''"))
    reason: Mapped[str] = mapped_column(String(128), nullable=False, server_default=text("''"))
    extra: Mapped[dict | None] = mapped_column(JsonType, nullable=True)


class CustomerAiOutboxRow(Base):
    __tablename__ = "customer_ai_outbox"
    __table_args__ = (Index("ix_customer_ai_outbox_state_id", "state", "outbox_id"),)

    outbox_id: Mapped[str] = mapped_column(String(220), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    operation_id: Mapped[str] = mapped_column(String(160), nullable=False, server_default=text("''"))
    reservation_id: Mapped[str] = mapped_column(String(160), nullable=False, server_default=text("''"))
    billing_policy: Mapped[str] = mapped_column(String(32), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    envelope: Mapped[dict] = mapped_column(JsonType, nullable=False)
    provider_message_id: Mapped[str] = mapped_column(String(160), nullable=False, server_default=text("''"))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    updated_at: Mapped[str] = mapped_column(String(64), nullable=False)
    extra: Mapped[dict | None] = mapped_column(JsonType, nullable=True)


class CustomerAiConversationRow(Base):
    __tablename__ = "customer_ai_conversations"
    __table_args__ = (Index("ix_customer_ai_conversations_tenant", "tenant_id"),)

    store_key: Mapped[str] = mapped_column(String(384), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    conversation_id: Mapped[str] = mapped_column(String(320), nullable=False, server_default=text("''"))
    state: Mapped[dict] = mapped_column(JsonType, nullable=False)
    pending: Mapped[list | None] = mapped_column(JsonType, nullable=True)
    history: Mapped[list | None] = mapped_column(JsonType, nullable=True)
    updated_at: Mapped[str] = mapped_column(String(64), nullable=False)


class CustomerAiCatalogAdminRow(Base):
    __tablename__ = "customer_ai_catalog_admin"

    row_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    draft: Mapped[dict] = mapped_column(JsonType, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    published: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    audit: Mapped[list | None] = mapped_column(JsonType, nullable=True)
    updated_at: Mapped[str] = mapped_column(String(64), nullable=False)


class CustomerAiCreditReservationIndexRow(Base):
    __tablename__ = "customer_ai_credit_reservation_index"
    __table_args__ = (Index("ix_credit_reservation_index_tenant_state", "tenant_id", "state"),)

    reservation_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    request_id: Mapped[str] = mapped_column(String(160), nullable=False, server_default=text("''"))
    operation_type: Mapped[str] = mapped_column(String(64), nullable=False, server_default=text("''"))
    created_at: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'reserved'"))


class CustomerAiProcessingAttemptRow(Base):
    __tablename__ = "customer_ai_processing_attempts"

    tenant_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    day_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    used: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    updated_at: Mapped[str] = mapped_column(String(64), nullable=False)


class CustomerAiProcessingJobRow(Base):
    __tablename__ = "customer_ai_processing_jobs"
    __table_args__ = (Index("ix_processing_jobs_tenant_created", "tenant_id", "created_at"),)

    job_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[str] = mapped_column(String(64), nullable=False)
