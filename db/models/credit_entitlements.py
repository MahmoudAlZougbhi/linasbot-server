"""Credit ledger + tenant entitlements ORM (PostgreSQL SoT).

Additive tables for LINAS_BILLING_BACKEND=postgres (code default postgres; set file for local/dev).
Covers Apple/Google/admin entitlement effects + credit packs.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import BigInteger, Float, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from db.models.base import Base

JsonType = JSON().with_variant(JSONB(), "postgresql")


class CreditBalanceRow(Base):
    __tablename__ = "credit_balances"

    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    available: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    reserved: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    updated_at: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0"))


class CreditLedgerEntryRow(Base):
    __tablename__ = "credit_ledger_entries"
    __table_args__ = (
        Index("ix_credit_ledger_entries_tenant_created", "tenant_id", "created_at"),
        Index("ix_credit_ledger_entries_tenant_request", "tenant_id", "request_id"),
        # Partial unique: idempotent grant/reverse/capture under concurrency (NULL request_id excluded).
        Index(
            "uq_credit_ledger_tenant_request_op",
            "tenant_id",
            "request_id",
            "op",
            unique=True,
            postgresql_where=text("request_id IS NOT NULL"),
            sqlite_where=text("request_id IS NOT NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    op: Mapped[str] = mapped_column(String(32), nullable=False)
    credits: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    balance_after: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    operation_type: Mapped[str] = mapped_column(String(64), nullable=False, server_default=text("''"))
    model_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0"))
    meta: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False, server_default=text("'{}'"))


class TenantEntitlementRow(Base):
    __tablename__ = "tenant_entitlements"

    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    plan_id: Mapped[str] = mapped_column(String(64), nullable=False, server_default=text("'none'"))
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'none'"))
    source: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'none'"))
    current_period_end: Mapped[float | None] = mapped_column(Float, nullable=True)
    included_credits: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    extra_credits: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    features: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False, server_default=text("'{}'"))
    updated_at: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0"))
    store_original_transaction_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    pending_plan_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pending_plan_effective_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    pending_plan_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pending_plan_effective_at: Mapped[float | None] = mapped_column(Float, nullable=True)


class EntitlementProcessedEventRow(Base):
    __tablename__ = "entitlement_processed_events"

    idempotency_key: Mapped[str] = mapped_column(String(255), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0"))
    meta: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False, server_default=text("'{}'"))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
