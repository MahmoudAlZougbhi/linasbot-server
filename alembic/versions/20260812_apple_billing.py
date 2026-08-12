"""Apple billing + auth identity tables (additive Postgres SoT).

Revision ID: 20260812_apple_billing
Revises: 20260812_credit_entitlements
Create Date: 2026-08-12

Note: Apple tables are intentionally chained BEFORE Customer Requests so
managed PG can apply Apple identity/billing without applying Requests.

Upgrade:
  - auth_external_identities, apple_app_account_tokens, apple_transactions,
    apple_notification_events, apple_credit_grants.
  - Additive only; Postgres is the sole SoT for these Apple tables
    (no file-backed financial store).

Rollback:
  - downgrade() drops the new tables in FK-safe order.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260812_apple_billing"
down_revision: str | None = "20260812_credit_entitlements"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JsonType = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "auth_external_identities",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_subject", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column(
            "email_is_private_relay",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("linked_at", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("unlinked_at", sa.Float(), nullable=True),
        sa.Column("meta", JsonType, nullable=False, server_default=sa.text("'{}'")),
        sa.UniqueConstraint(
            "provider",
            "provider_subject",
            name="uq_auth_ext_identity_provider_subject",
        ),
    )
    op.create_index(
        "ix_auth_external_identities_tenant_id",
        "auth_external_identities",
        ["tenant_id"],
    )
    op.create_index(
        "ix_auth_external_identities_user_id",
        "auth_external_identities",
        ["user_id"],
    )

    op.create_table(
        "apple_app_account_tokens",
        sa.Column("app_account_token", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.UniqueConstraint(
            "tenant_id",
            "user_id",
            name="uq_apple_app_account_token_tenant_user",
        ),
    )

    op.create_table(
        "apple_transactions",
        sa.Column("transaction_id", sa.String(length=128), primary_key=True),
        sa.Column("original_transaction_id", sa.String(length=128), nullable=False),
        sa.Column("product_id", sa.String(length=128), nullable=False),
        sa.Column("environment", sa.String(length=32), nullable=False),
        sa.Column("bundle_id", sa.String(length=128), nullable=False),
        sa.Column("app_account_token", sa.String(length=36), nullable=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=True),
        sa.Column("user_id", sa.String(length=128), nullable=True),
        sa.Column("purchase_date_ms", sa.BigInteger(), nullable=True),
        sa.Column("expires_date_ms", sa.BigInteger(), nullable=True),
        sa.Column("revocation_date_ms", sa.BigInteger(), nullable=True),
        sa.Column("transaction_reason", sa.String(length=64), nullable=True),
        sa.Column("subscription_group_id", sa.String(length=64), nullable=True),
        sa.Column("type", sa.String(length=64), nullable=False, server_default=sa.text("''")),
        sa.Column("signed_payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("processing_status", sa.String(length=32), nullable=False),
        sa.Column("first_seen_at", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_seen_at", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("effect", JsonType, nullable=False, server_default=sa.text("'{}'")),
    )
    op.create_index(
        "ix_apple_transactions_original_transaction_id",
        "apple_transactions",
        ["original_transaction_id"],
    )
    op.create_index(
        "ix_apple_transactions_tenant_id",
        "apple_transactions",
        ["tenant_id"],
    )

    op.create_table(
        "apple_notification_events",
        sa.Column("notification_uuid", sa.String(length=64), primary_key=True),
        sa.Column("notification_type", sa.String(length=64), nullable=False),
        sa.Column("subtype", sa.String(length=64), nullable=True),
        sa.Column("environment", sa.String(length=32), nullable=False),
        sa.Column("signed_payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("processing_status", sa.String(length=32), nullable=False),
        sa.Column("first_seen_at", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_seen_at", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("result", JsonType, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("related_transaction_id", sa.String(length=128), nullable=True),
    )

    op.create_table(
        "apple_credit_grants",
        sa.Column("transaction_id", sa.String(length=128), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("product_id", sa.String(length=128), nullable=False),
        sa.Column("credits", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("granted_at", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("reversed_at", sa.Float(), nullable=True),
        sa.Column("ledger_entry_id", sa.String(length=36), nullable=True),
        sa.Column("meta", JsonType, nullable=False, server_default=sa.text("'{}'")),
    )
    op.create_index(
        "ix_apple_credit_grants_tenant_id",
        "apple_credit_grants",
        ["tenant_id"],
    )


def downgrade() -> None:
    op.drop_table("apple_credit_grants")
    op.drop_table("apple_notification_events")
    op.drop_table("apple_transactions")
    op.drop_table("apple_app_account_tokens")
    op.drop_table("auth_external_identities")
