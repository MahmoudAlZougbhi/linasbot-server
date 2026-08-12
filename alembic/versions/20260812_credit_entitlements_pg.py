"""Additive credit balances + entitlements tables for LINAS_BILLING_BACKEND=postgres.

Revision ID: 20260812_credit_entitlements
Revises: 20260812_ha_billing_auth
Create Date: 2026-08-12

Do NOT set LINAS_BILLING_BACKEND=postgres on production without import + approval.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260812_credit_entitlements"
down_revision: str | None = "20260812_ha_billing_auth"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JsonType = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "credit_balances",
        sa.Column("tenant_id", sa.String(length=64), primary_key=True),
        sa.Column("available", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("reserved", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("updated_at", sa.Float(), nullable=False, server_default=sa.text("0")),
    )

    op.create_table(
        "credit_ledger_entries",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=True),
        sa.Column("op", sa.String(length=32), nullable=False),
        sa.Column("credits", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("balance_after", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("operation_type", sa.String(length=64), nullable=False, server_default=sa.text("''")),
        sa.Column("model_provider", sa.String(length=64), nullable=True),
        sa.Column("provider_cost_usd", sa.Float(), nullable=True),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("meta", JsonType, nullable=False, server_default=sa.text("'{}'")),
    )
    op.create_index(
        "ix_credit_ledger_entries_tenant_created",
        "credit_ledger_entries",
        ["tenant_id", "created_at"],
    )
    op.create_index(
        "ix_credit_ledger_entries_tenant_request",
        "credit_ledger_entries",
        ["tenant_id", "request_id"],
    )
    op.create_index(
        "uq_credit_ledger_tenant_request_op",
        "credit_ledger_entries",
        ["tenant_id", "request_id", "op"],
        unique=True,
        postgresql_where=sa.text("request_id IS NOT NULL"),
        sqlite_where=sa.text("request_id IS NOT NULL"),
    )

    op.create_table(
        "tenant_entitlements",
        sa.Column("tenant_id", sa.String(length=64), primary_key=True),
        sa.Column("plan_id", sa.String(length=64), nullable=False, server_default=sa.text("'none'")),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'none'")),
        sa.Column("source", sa.String(length=32), nullable=False, server_default=sa.text("'none'")),
        sa.Column("current_period_end", sa.Float(), nullable=True),
        sa.Column("included_credits", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("extra_credits", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("features", JsonType, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("updated_at", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("store_original_transaction_id", sa.String(length=128), nullable=True),
    )

    op.create_table(
        "entitlement_processed_events",
        sa.Column("idempotency_key", sa.String(length=255), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("meta", JsonType, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("note", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("entitlement_processed_events")
    op.drop_table("tenant_entitlements")
    op.drop_index("ix_credit_ledger_entries_tenant_request", table_name="credit_ledger_entries")
    op.drop_index("ix_credit_ledger_entries_tenant_created", table_name="credit_ledger_entries")
    op.drop_table("credit_ledger_entries")
    op.drop_table("credit_balances")
