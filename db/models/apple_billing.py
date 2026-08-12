"""Apple billing + auth identity ORM models (PostgreSQL SoT only).

Additive tables for Sign in with Apple linkage, appAccountToken binding,
StoreKit / ASSN transaction idempotency, and credit grant ledger.

No file-backed financial source of truth for these tables.

AuthExternalIdentityRow unlink policy
-------------------------------------
UniqueConstraint(provider, provider_subject) always applies (no partial unique).

- Unlink sets ``unlinked_at`` but keeps the row and the same ``provider_subject``.
- The same Apple ``sub`` cannot be linked to a different user without admin
  intervention (unique still blocks a second row).
- Re-link for the *same* user after unlink: clear ``unlinked_at`` on the
  existing row (do not insert a duplicate).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import BigInteger, Boolean, Float, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from db.models.base import Base

JsonType = JSON().with_variant(JSONB(), "postgresql")


class AuthExternalIdentityRow(Base):
    __tablename__ = "auth_external_identities"
    __table_args__ = (
        UniqueConstraint("provider", "provider_subject", name="uq_auth_ext_identity_provider_subject"),
        Index("ix_auth_external_identities_tenant_id", "tenant_id"),
        Index("ix_auth_external_identities_user_id", "user_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    email_is_private_relay: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    linked_at: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0"))
    unlinked_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    meta: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False, server_default=text("'{}'"))


class AppleAppAccountTokenRow(Base):
    """One stable appAccountToken UUID string per (tenant_id, user_id)."""

    __tablename__ = "apple_app_account_tokens"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", name="uq_apple_app_account_token_tenant_user"),
    )

    app_account_token: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0"))


class AppleTransactionRow(Base):
    __tablename__ = "apple_transactions"
    __table_args__ = (
        Index("ix_apple_transactions_original_transaction_id", "original_transaction_id"),
        Index("ix_apple_transactions_tenant_id", "tenant_id"),
    )

    transaction_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    original_transaction_id: Mapped[str] = mapped_column(String(128), nullable=False)
    product_id: Mapped[str] = mapped_column(String(128), nullable=False)
    environment: Mapped[str] = mapped_column(String(32), nullable=False)
    bundle_id: Mapped[str] = mapped_column(String(128), nullable=False)
    app_account_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    tenant_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    purchase_date_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    expires_date_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    revocation_date_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    transaction_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    subscription_group_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    type: Mapped[str] = mapped_column(String(64), nullable=False, server_default=text("''"))
    signed_payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    processing_status: Mapped[str] = mapped_column(String(32), nullable=False)
    first_seen_at: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0"))
    last_seen_at: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0"))
    effect: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False, server_default=text("'{}'"))


class AppleNotificationEventRow(Base):
    __tablename__ = "apple_notification_events"

    notification_uuid: Mapped[str] = mapped_column(String(64), primary_key=True)
    notification_type: Mapped[str] = mapped_column(String(64), nullable=False)
    subtype: Mapped[str | None] = mapped_column(String(64), nullable=True)
    environment: Mapped[str] = mapped_column(String(32), nullable=False)
    signed_payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    processing_status: Mapped[str] = mapped_column(String(32), nullable=False)
    first_seen_at: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0"))
    last_seen_at: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0"))
    result: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False, server_default=text("'{}'"))
    related_transaction_id: Mapped[str | None] = mapped_column(String(128), nullable=True)


class AppleCreditGrantRow(Base):
    """Idempotent credit grant keyed by Apple transaction_id."""

    __tablename__ = "apple_credit_grants"
    __table_args__ = (Index("ix_apple_credit_grants_tenant_id", "tenant_id"),)

    transaction_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    product_id: Mapped[str] = mapped_column(String(128), nullable=False)
    credits: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    granted_at: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0"))
    reversed_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    ledger_entry_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    meta: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False, server_default=text("'{}'"))
