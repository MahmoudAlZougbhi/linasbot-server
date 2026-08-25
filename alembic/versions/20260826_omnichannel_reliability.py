"""Durable omnichannel inbound ledger + outbound outbox (PostgreSQL SoT).

Revision ID: 20260826_omnichannel_rel
Revises: 20260826_meta_comment_perm
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260826_omnichannel_rel"
down_revision: str | None = "20260826_meta_comment_perm"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JsonType = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "omnichannel_inbound_events",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("provider_event_id", sa.String(length=128), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("account_id", sa.String(length=128), nullable=False, server_default=sa.text("''")),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("surface", sa.String(length=32), nullable=False),
        sa.Column("conversation_key", sa.String(length=255), nullable=False),
        sa.Column("provider_timestamp", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False, server_default=sa.text("'accepted'")),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("queue_job_id", sa.String(length=64), nullable=True),
        sa.Column("last_error", sa.String(length=255), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payload", JsonType, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "tenant_id", "channel", "surface", "provider_event_id", name="uq_omni_inbound_provider_event"
        ),
        sa.CheckConstraint(
            "state IN ('accepted','queued','generating','reply_ready','rate_limited',"
            "'sending','delivered','reconciliation_required','failed','dead_letter')",
            name="ck_omni_inbound_state",
        ),
    )
    op.create_index("ix_omni_inbound_tenant_state", "omnichannel_inbound_events", ["tenant_id", "state"])
    op.create_index("ix_omni_inbound_conversation", "omnichannel_inbound_events", ["conversation_key"])
    op.create_index("ix_omni_inbound_next_retry", "omnichannel_inbound_events", ["next_retry_at"])

    op.create_table(
        "omnichannel_outbound_outbox",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("surface", sa.String(length=32), nullable=False),
        sa.Column("account_id", sa.String(length=128), nullable=False, server_default=sa.text("''")),
        sa.Column("conversation_key", sa.String(length=255), nullable=False),
        sa.Column("inbound_event_id", sa.String(length=64), nullable=True),
        sa.Column("canonical_body", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("idempotency_key", sa.String(length=191), nullable=False),
        sa.Column("control_epoch", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("credit_reservation_id", sa.String(length=128), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_message_id", sa.String(length=128), nullable=True),
        sa.Column("provider_request_id", sa.String(length=128), nullable=True),
        sa.Column("state", sa.String(length=32), nullable=False, server_default=sa.text("'queued'")),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_subcode", sa.String(length=64), nullable=True),
        sa.Column("last_error", sa.String(length=255), nullable=True),
        sa.Column("source", sa.String(length=16), nullable=False, server_default=sa.text("'ai'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("regenerated", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.UniqueConstraint("idempotency_key", name="uq_omni_outbound_idempotency"),
        sa.CheckConstraint(
            "state IN ('queued','rate_limited','sending','delivered',"
            "'reconciliation_required','failed','dead_letter','needs_owner_action')",
            name="ck_omni_outbound_state",
        ),
    )
    op.create_index("ix_omni_outbound_tenant_state", "omnichannel_outbound_outbox", ["tenant_id", "state"])
    op.create_index("ix_omni_outbound_inbound", "omnichannel_outbound_outbox", ["inbound_event_id"])
    op.create_index("ix_omni_outbound_next_retry", "omnichannel_outbound_outbox", ["next_retry_at"])

    op.add_column(
        "tiktok_comments",
        sa.Column("ai_claimed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "whatsapp_outbound_intents",
        sa.Column("canonical_text", sa.Text(), nullable=False, server_default=sa.text("''")),
    )
    op.add_column(
        "whatsapp_outbound_intents",
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "whatsapp_outbound_intents",
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("whatsapp_outbound_intents", "next_retry_at")
    op.drop_column("whatsapp_outbound_intents", "attempt_count")
    op.drop_column("whatsapp_outbound_intents", "canonical_text")
    op.drop_column("tiktok_comments", "ai_claimed_at")
    op.drop_index("ix_omni_outbound_next_retry", table_name="omnichannel_outbound_outbox")
    op.drop_index("ix_omni_outbound_inbound", table_name="omnichannel_outbound_outbox")
    op.drop_index("ix_omni_outbound_tenant_state", table_name="omnichannel_outbound_outbox")
    op.drop_table("omnichannel_outbound_outbox")
    op.drop_index("ix_omni_inbound_next_retry", table_name="omnichannel_inbound_events")
    op.drop_index("ix_omni_inbound_conversation", table_name="omnichannel_inbound_events")
    op.drop_index("ix_omni_inbound_tenant_state", table_name="omnichannel_inbound_events")
    op.drop_table("omnichannel_inbound_events")
