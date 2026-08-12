"""Billing + auth token ORM models (PostgreSQL SoT).

Additive tables for LINAS_BILLING_BACKEND=postgres and
LINAS_AUTH_TOKEN_BACKEND=postgres. File stores remain default until cutover.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import BigInteger, Boolean, Float, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from db.models.base import Base

JsonType = JSON().with_variant(JSONB(), "postgresql")


class TokenWalletRow(Base):
    __tablename__ = "token_wallets"

    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    input_remaining: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    output_remaining: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    lifetime_input_credited: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    lifetime_output_credited: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    lifetime_input_debited: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    lifetime_output_debited: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    lifetime_spent_usd: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0"))
    balance_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    lifetime_credited: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    lifetime_debited: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("2"))
    migrated_from_legacy: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    migration_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    legacy_balance_tokens_before_migration: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    updated_at: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0"))


class TokenWalletLedgerRow(Base):
    __tablename__ = "token_wallet_ledger"
    __table_args__ = (Index("ix_token_wallet_ledger_tenant_created", "tenant_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0"))
    payload: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False, server_default=text("'{}'"))


class StripeProcessedEventRow(Base):
    __tablename__ = "stripe_processed_events"

    event_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    created_at: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0"))
    meta: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False, server_default=text("'{}'"))


class AdminCreditIdempotencyRow(Base):
    __tablename__ = "admin_credit_idempotency"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    created_at: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0"))
    meta: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False, server_default=text("'{}'"))


class MobileRefreshTokenRow(Base):
    __tablename__ = "mobile_refresh_tokens"
    __table_args__ = (
        Index("ix_mobile_refresh_tokens_tenant_id", "tenant_id"),
        Index("ix_mobile_refresh_tokens_user_id", "user_id"),
    )

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False, server_default=text("''"))
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    session_id: Mapped[str] = mapped_column(String(128), nullable=False, server_default=text("''"))
    created_at: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0"))
    expires_at: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0"))
    revoked_at: Mapped[float | None] = mapped_column(Float, nullable=True)


class AuthEmailTokenRow(Base):
    __tablename__ = "auth_email_tokens"
    __table_args__ = (
        Index("ix_auth_email_tokens_tenant_id", "tenant_id"),
        Index("ix_auth_email_tokens_user_id", "user_id"),
    )

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False, server_default=text("''"))
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0"))
    expires_at: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0"))
    used_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    meta: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
