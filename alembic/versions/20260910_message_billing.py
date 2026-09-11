"""Message ledger, daily AI Setup edits, and internal expense journal.

Revision ID: 20260910_msg_billing
Revises: 20260910_cust_ai_search

Durable tables only. Live credit entitlements are not converted or deleted.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260910_msg_billing"
down_revision: str | None = "20260910_cust_ai_search"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JsonType = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "customer_ai_message_lots",
        sa.Column("lot_id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("period_id", sa.String(length=64), nullable=False),
        sa.Column("granted", sa.Integer(), nullable=False),
        sa.Column("remaining", sa.Integer(), nullable=False),
        sa.Column("expires", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("catalog_version", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_message_lots_tenant", "customer_ai_message_lots", ["tenant_id"])

    op.create_table(
        "customer_ai_message_reservations",
        sa.Column("reservation_id", sa.String(length=160), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("operation_id", sa.String(length=128), nullable=False),
        sa.Column("units", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("lot_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("period_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("response_class", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "operation_id", name="uq_message_reservation_op"),
    )
    op.create_index(
        "ix_message_reservations_status_created",
        "customer_ai_message_reservations",
        ["status", "created_at"],
    )

    op.create_table(
        "customer_ai_daily_edits",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("window_id", sa.String(length=16), nullable=False),
        sa.Column("operation_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "window_id", "operation_id", name="uq_daily_edit_op"),
    )
    op.create_index("ix_daily_edits_tenant_window", "customer_ai_daily_edits", ["tenant_id", "window_id"])

    op.create_table(
        "customer_ai_daily_edit_policies",
        sa.Column("tenant_id", sa.String(length=128), primary_key=True),
        sa.Column("limit_value", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="tenant_override"),
        sa.Column("actor", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("reason", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "customer_ai_expense_events",
        sa.Column("event_id", sa.String(length=128), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("feature", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("amount_usd", sa.Numeric(12, 6), nullable=True),
        sa.Column("quantity", sa.Numeric(16, 6), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("environment", sa.String(length=16), nullable=False, server_default="test"),
        sa.Column("operation_id", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("parent_event_id", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("extra", JsonType, nullable=True),
    )
    op.create_index("ix_expense_events_tenant", "customer_ai_expense_events", ["tenant_id"])

    op.create_table(
        "customer_ai_pending_settlements",
        sa.Column("settlement_id", sa.String(length=220), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("reservation_id", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("operation_id", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("billing_policy", sa.String(length=32), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.String(length=64), nullable=False),
        sa.Column("updated_at", sa.String(length=64), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("send_status", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("provider_message_id", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("channel", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("reason", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("extra", JsonType, nullable=True),
    )
    op.create_index(
        "ix_pending_settlements_state_id",
        "customer_ai_pending_settlements",
        ["state", "settlement_id"],
    )

    op.create_table(
        "customer_ai_outbox",
        sa.Column("outbox_id", sa.String(length=220), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("operation_id", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("reservation_id", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("billing_policy", sa.String(length=32), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("envelope", JsonType, nullable=False),
        sa.Column("provider_message_id", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.String(length=64), nullable=False),
        sa.Column("extra", JsonType, nullable=True),
    )
    op.create_index("ix_customer_ai_outbox_state_id", "customer_ai_outbox", ["state", "outbox_id"])

    op.create_table(
        "customer_ai_conversations",
        sa.Column("store_key", sa.String(length=384), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("conversation_id", sa.String(length=320), nullable=False, server_default=""),
        sa.Column("state", JsonType, nullable=False),
        sa.Column("pending", JsonType, nullable=True),
        sa.Column("history", JsonType, nullable=True),
        sa.Column("updated_at", sa.String(length=64), nullable=False),
    )
    op.create_index("ix_customer_ai_conversations_tenant", "customer_ai_conversations", ["tenant_id"])

    op.create_table(
        "customer_ai_catalog_admin",
        sa.Column("row_id", sa.String(length=32), primary_key=True),
        sa.Column("draft", JsonType, nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("published", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("audit", JsonType, nullable=True),
        sa.Column("updated_at", sa.String(length=64), nullable=False),
    )

    op.create_table(
        "customer_ai_credit_reservation_index",
        sa.Column("reservation_id", sa.String(length=160), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("request_id", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("operation_type", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False, server_default="reserved"),
    )
    op.create_index(
        "ix_credit_reservation_index_tenant_state",
        "customer_ai_credit_reservation_index",
        ["tenant_id", "state"],
    )

    op.create_table(
        "customer_ai_processing_attempts",
        sa.Column("tenant_id", sa.String(length=128), primary_key=True),
        sa.Column("day_id", sa.String(length=16), primary_key=True),
        sa.Column("used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.String(length=64), nullable=False),
    )
    op.create_table(
        "customer_ai_processing_jobs",
        sa.Column("job_id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.String(length=64), nullable=False),
    )
    op.create_index("ix_processing_jobs_tenant_created", "customer_ai_processing_jobs", ["tenant_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_processing_jobs_tenant_created", table_name="customer_ai_processing_jobs")
    op.drop_table("customer_ai_processing_jobs")
    op.drop_table("customer_ai_processing_attempts")
    op.drop_index(
        "ix_credit_reservation_index_tenant_state",
        table_name="customer_ai_credit_reservation_index",
    )
    op.drop_table("customer_ai_credit_reservation_index")
    op.drop_table("customer_ai_catalog_admin")
    op.drop_index("ix_customer_ai_conversations_tenant", table_name="customer_ai_conversations")
    op.drop_table("customer_ai_conversations")
    op.drop_index("ix_customer_ai_outbox_state_id", table_name="customer_ai_outbox")
    op.drop_table("customer_ai_outbox")
    op.drop_index("ix_pending_settlements_state_id", table_name="customer_ai_pending_settlements")
    op.drop_table("customer_ai_pending_settlements")
    op.drop_table("customer_ai_expense_events")
    op.drop_table("customer_ai_daily_edit_policies")
    op.drop_table("customer_ai_daily_edits")
    op.drop_index("ix_message_reservations_status_created", table_name="customer_ai_message_reservations")
    op.drop_table("customer_ai_message_reservations")
    op.drop_table("customer_ai_message_lots")
