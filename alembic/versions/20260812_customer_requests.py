"""Customer Requests domain tables (additive).

Revision ID: 20260812_customer_requests
Revises: 20260811_wa_app_review_source
Create Date: 2026-08-12

Upgrade:
  - Creates tenant-scoped request, event, note, outbox, idempotency, and counter tables.
  - Additive only; no rewrite of existing WhatsApp Cloud data.
  - Safe for existing tenants (empty tables; AI capture remains gated by published CM).

Do NOT apply to production in Phase 1 — Phase 13 owns production migration.

Rollback:
  - downgrade() drops the new tables in FK-safe order.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260812_customer_requests"
down_revision: str | None = "20260811_wa_app_review_source"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JsonType = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "customer_requests",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("request_number", sa.String(length=32), nullable=False),
        sa.Column("request_type", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'NEW'")),
        sa.Column("source_channel", sa.String(length=32), nullable=False),
        sa.Column("source_account_id", sa.String(length=128), nullable=True),
        sa.Column("external_customer_id", sa.String(length=128), nullable=True),
        sa.Column("platform_username", sa.String(length=256), nullable=True),
        sa.Column("customer_display_name", sa.String(length=256), nullable=True),
        sa.Column("customer_name", sa.String(length=256), nullable=True),
        sa.Column("phone_normalized", sa.String(length=32), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("conversation_id", sa.String(length=128), nullable=True),
        sa.Column("originating_message_id", sa.String(length=128), nullable=True),
        sa.Column("originating_comment_id", sa.String(length=128), nullable=True),
        sa.Column("title", sa.String(length=512), nullable=True),
        sa.Column("collected_fields", JsonType, nullable=True),
        sa.Column("requested_items", JsonType, nullable=True),
        sa.Column("requested_branch", sa.String(length=256), nullable=True),
        sa.Column("preferred_date", sa.String(length=32), nullable=True),
        sa.Column("preferred_time", sa.String(length=64), nullable=True),
        sa.Column("fulfillment_preference", sa.String(length=32), nullable=True),
        sa.Column("delivery_address", sa.Text(), nullable=True),
        sa.Column("customer_notes", sa.Text(), nullable=True),
        sa.Column("assigned_user_id", sa.String(length=128), nullable=True),
        sa.Column("configuration_version", sa.String(length=64), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column(
            "notification_status",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'none'"),
        ),
        sa.Column("last_notification_error", sa.String(length=512), nullable=True),
        sa.Column("completion_message", sa.Text(), nullable=True),
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
        sa.Column("manual_mode_conversation_ref", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ready_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("tenant_id", "request_number", name="uq_customer_requests_tenant_number"),
        sa.CheckConstraint(
            "request_type IN ('ORDER','APPOINTMENT','OTHER')",
            name="ck_customer_requests_type",
        ),
        sa.CheckConstraint(
            "status IN ("
            "'NEW','IN_REVIEW','WAITING_FOR_CUSTOMER',"
            "'CONFIRMED','READY','COMPLETED','CANCELLED')",
            name="ck_customer_requests_status",
        ),
        sa.CheckConstraint(
            "source_channel IN ("
            "'instagram_dm','facebook_messenger',"
            "'whatsapp_cloud','comment_linked_dm')",
            name="ck_customer_requests_channel",
        ),
        sa.CheckConstraint(
            "notification_status IN ('none','pending','sent','failed','blocked')",
            name="ck_customer_requests_notification_status",
        ),
    )
    op.create_index("ix_customer_requests_tenant_id", "customer_requests", ["tenant_id"])
    op.create_index(
        "ix_customer_requests_tenant_status_created",
        "customer_requests",
        ["tenant_id", "status", "created_at"],
    )
    op.create_index(
        "ix_customer_requests_tenant_type_created",
        "customer_requests",
        ["tenant_id", "request_type", "created_at"],
    )
    op.create_index(
        "ix_customer_requests_tenant_assignee_created",
        "customer_requests",
        ["tenant_id", "assigned_user_id", "created_at"],
    )
    op.create_index(
        "ix_customer_requests_tenant_channel_created",
        "customer_requests",
        ["tenant_id", "source_channel", "created_at"],
    )
    op.create_index(
        "ix_customer_requests_tenant_phone",
        "customer_requests",
        ["tenant_id", "phone_normalized"],
    )
    op.create_index(
        "ix_customer_requests_tenant_conversation",
        "customer_requests",
        ["tenant_id", "conversation_id"],
    )

    op.create_table(
        "customer_request_counters",
        sa.Column("tenant_id", sa.String(length=64), primary_key=True),
        sa.Column("next_number", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    op.create_table(
        "customer_request_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column(
            "request_id",
            sa.String(length=36),
            sa.ForeignKey("customer_requests.id"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("actor_user_id", sa.String(length=128), nullable=True),
        sa.Column("actor_kind", sa.String(length=16), nullable=False, server_default=sa.text("'system'")),
        sa.Column("payload", JsonType, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint(
            "actor_kind IN ('system','ai','operator','customer')",
            name="ck_customer_request_events_actor_kind",
        ),
    )
    op.create_index("ix_customer_request_events_tenant_id", "customer_request_events", ["tenant_id"])
    op.create_index(
        "ix_customer_request_events_tenant_request_created",
        "customer_request_events",
        ["tenant_id", "request_id", "created_at"],
    )

    op.create_table(
        "customer_request_notes",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column(
            "request_id",
            sa.String(length=36),
            sa.ForeignKey("customer_requests.id"),
            nullable=False,
        ),
        sa.Column("author_user_id", sa.String(length=128), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_customer_request_notes_tenant_id", "customer_request_notes", ["tenant_id"])
    op.create_index(
        "ix_customer_request_notes_tenant_request_created",
        "customer_request_notes",
        ["tenant_id", "request_id", "created_at"],
    )

    op.create_table(
        "customer_request_outbox",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column(
            "request_id",
            sa.String(length=36),
            sa.ForeignKey("customer_requests.id"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("payload", JsonType, nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_error", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_customer_request_outbox_idem"),
        sa.CheckConstraint(
            "status IN ('pending','sent','failed','blocked','cancelled')",
            name="ck_customer_request_outbox_status",
        ),
    )
    op.create_index("ix_customer_request_outbox_tenant_id", "customer_request_outbox", ["tenant_id"])
    op.create_index(
        "ix_customer_request_outbox_tenant_request",
        "customer_request_outbox",
        ["tenant_id", "request_id"],
    )
    op.create_index(
        "ix_customer_request_outbox_tenant_status",
        "customer_request_outbox",
        ["tenant_id", "status"],
    )

    op.create_table(
        "customer_request_idempotency",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("scope", sa.String(length=64), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("request_id", sa.String(length=36), nullable=True),
        sa.Column("response_fingerprint", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint(
            "tenant_id",
            "scope",
            "key",
            name="uq_customer_request_idempotency_scope_key",
        ),
    )
    op.create_index(
        "ix_customer_request_idempotency_tenant_id",
        "customer_request_idempotency",
        ["tenant_id"],
    )
    op.create_index(
        "ix_customer_request_idempotency_tenant_request",
        "customer_request_idempotency",
        ["tenant_id", "request_id"],
    )


def downgrade() -> None:
    op.drop_table("customer_request_idempotency")
    op.drop_table("customer_request_outbox")
    op.drop_table("customer_request_notes")
    op.drop_table("customer_request_events")
    op.drop_table("customer_request_counters")
    op.drop_table("customer_requests")
