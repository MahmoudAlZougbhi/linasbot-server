"""HA billing + auth token tables (additive Postgres SoT).

Revision ID: 20260812_ha_billing_auth
Revises: 20260812_meta_app_registry
Create Date: 2026-08-12

Upgrade:
  - token_wallets, token_wallet_ledger, stripe_processed_events,
    admin_credit_idempotency, mobile_refresh_tokens, auth_email_tokens.
  - Additive only; file-backed stores remain default until env cutover.

Do NOT set LINAS_BILLING_BACKEND=postgres or LINAS_AUTH_TOKEN_BACKEND=postgres
on production without import + approval.

Rollback:
  - downgrade() drops the new tables in FK-safe order.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260812_ha_billing_auth"
down_revision: str | None = "20260812_meta_app_registry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JsonType = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "token_wallets",
        sa.Column("tenant_id", sa.String(length=64), primary_key=True),
        sa.Column("input_remaining", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("output_remaining", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "lifetime_input_credited",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "lifetime_output_credited",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "lifetime_input_debited",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "lifetime_output_debited",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("lifetime_spent_usd", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("balance_tokens", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("lifetime_credited", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("lifetime_debited", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default=sa.text("2")),
        sa.Column(
            "migrated_from_legacy",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("migration_note", sa.Text(), nullable=True),
        sa.Column("legacy_balance_tokens_before_migration", sa.BigInteger(), nullable=True),
        sa.Column("updated_at", sa.Float(), nullable=False, server_default=sa.text("0")),
    )

    op.create_table(
        "token_wallet_ledger",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("payload", JsonType, nullable=False, server_default=sa.text("'{}'")),
    )
    op.create_index("ix_token_wallet_ledger_tenant_created", "token_wallet_ledger", ["tenant_id", "created_at"])

    op.create_table(
        "stripe_processed_events",
        sa.Column("event_id", sa.String(length=255), primary_key=True),
        sa.Column("created_at", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("meta", JsonType, nullable=False, server_default=sa.text("'{}'")),
    )

    op.create_table(
        "admin_credit_idempotency",
        sa.Column("key", sa.String(length=128), primary_key=True),
        sa.Column("created_at", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("meta", JsonType, nullable=False, server_default=sa.text("'{}'")),
    )

    op.create_table(
        "mobile_refresh_tokens",
        sa.Column("token_hash", sa.String(length=64), primary_key=True),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False, server_default=sa.text("''")),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=128), nullable=False, server_default=sa.text("''")),
        sa.Column("created_at", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("expires_at", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("revoked_at", sa.Float(), nullable=True),
    )
    op.create_index("ix_mobile_refresh_tokens_tenant_id", "mobile_refresh_tokens", ["tenant_id"])
    op.create_index("ix_mobile_refresh_tokens_user_id", "mobile_refresh_tokens", ["user_id"])

    op.create_table(
        "auth_email_tokens",
        sa.Column("token_hash", sa.String(length=64), primary_key=True),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False, server_default=sa.text("''")),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("expires_at", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("used_at", sa.Float(), nullable=True),
        sa.Column("meta", JsonType, nullable=True),
    )
    op.create_index("ix_auth_email_tokens_tenant_id", "auth_email_tokens", ["tenant_id"])
    op.create_index("ix_auth_email_tokens_user_id", "auth_email_tokens", ["user_id"])


def downgrade() -> None:
    op.drop_table("auth_email_tokens")
    op.drop_table("mobile_refresh_tokens")
    op.drop_table("admin_credit_idempotency")
    op.drop_table("stripe_processed_events")
    op.drop_table("token_wallet_ledger")
    op.drop_table("token_wallets")
