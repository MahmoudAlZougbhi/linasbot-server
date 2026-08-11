"""WhatsApp Smart Follow-Up domain tables.

Revision ID: 20260811_whatsapp_smart_followup
Revises: 20260811_whatsapp_cloud
Create Date: 2026-08-11
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260811_whatsapp_smart_followup"
down_revision: str | None = "20260811_whatsapp_cloud"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "whatsapp_smart_followup_settings",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("business_hours_only", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "billing_mode",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'customer_direct'"),
        ),
        sa.Column("updated_by_user_id", sa.String(length=128), nullable=True),
        sa.Column("settings_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("tenant_id", name="uq_wa_sfu_settings_tenant"),
        sa.CheckConstraint(
            "billing_mode IN ('customer_direct','solution_partner')",
            name="ck_wa_sfu_billing_mode",
        ),
    )

    op.create_table(
        "whatsapp_smart_followup_steps",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "settings_id",
            sa.String(length=36),
            sa.ForeignKey("whatsapp_smart_followup_settings.id"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("step_index", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("delay_minutes", sa.Integer(), nullable=False),
        sa.Column("goal", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("settings_id", "step_index", name="uq_wa_sfu_step_index"),
        sa.CheckConstraint("step_index >= 1 AND step_index <= 3", name="ck_wa_sfu_step_index"),
        sa.CheckConstraint("delay_minutes > 0", name="ck_wa_sfu_delay_positive"),
        sa.CheckConstraint(
            "goal IN ('gentle_check_in','offer_more_help','politely_close')",
            name="ck_wa_sfu_goal",
        ),
    )
    op.create_index("ix_wa_sfu_step_settings", "whatsapp_smart_followup_steps", ["settings_id"])
    op.create_index(
        "ix_whatsapp_smart_followup_steps_tenant_id",
        "whatsapp_smart_followup_steps",
        ["tenant_id"],
    )

    op.create_table(
        "whatsapp_smart_followup_sequences",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("connection_id", sa.String(length=36), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("trigger_outbound_intent_id", sa.String(length=36), nullable=False),
        sa.Column("trigger_ai_sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("control_epoch", sa.Integer(), nullable=False),
        sa.Column("settings_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'active'")),
        sa.Column("cancel_reason", sa.String(length=64), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint(
            "tenant_id",
            "conversation_id",
            "trigger_outbound_intent_id",
            name="uq_wa_sfu_sequence_trigger",
        ),
        sa.CheckConstraint(
            "status IN ('active','completed','cancelled','superseded')",
            name="ck_wa_sfu_sequence_status",
        ),
    )
    op.create_index(
        "ix_wa_sfu_seq_tenant_status",
        "whatsapp_smart_followup_sequences",
        ["tenant_id", "status"],
    )
    op.create_index(
        "ix_wa_sfu_seq_conversation",
        "whatsapp_smart_followup_sequences",
        ["conversation_id"],
    )

    op.create_table(
        "whatsapp_smart_followup_jobs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("connection_id", sa.String(length=36), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column(
            "sequence_id",
            sa.String(length=36),
            sa.ForeignKey("whatsapp_smart_followup_sequences.id"),
            nullable=False,
        ),
        sa.Column("step_index", sa.Integer(), nullable=False),
        sa.Column("goal", sa.String(length=32), nullable=False),
        sa.Column("delay_minutes", sa.Integer(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'scheduled'")),
        sa.Column("control_epoch", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claimed_by", sa.String(length=64), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("reservation_id", sa.String(length=64), nullable=True),
        sa.Column("provider_wamid", sa.String(length=128), nullable=True),
        sa.Column("result_reason", sa.String(length=64), nullable=True),
        sa.Column("result_detail", sa.String(length=255), nullable=True),
        sa.Column("credits_captured", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("idempotency_key", name="uq_wa_sfu_job_idempotency"),
        sa.UniqueConstraint("sequence_id", "step_index", name="uq_wa_sfu_job_sequence_step"),
        sa.CheckConstraint(
            "status IN ("
            "'scheduled','claimed','generating','sending','sent',"
            "'skipped','cancelled','failed','reconciliation_required'"
            ")",
            name="ck_wa_sfu_job_status",
        ),
    )
    op.create_index("ix_wa_sfu_job_due", "whatsapp_smart_followup_jobs", ["status", "due_at"])
    op.create_index("ix_wa_sfu_job_tenant", "whatsapp_smart_followup_jobs", ["tenant_id", "status"])
    op.create_index("ix_wa_sfu_job_conversation", "whatsapp_smart_followup_jobs", ["conversation_id"])

    op.create_table(
        "whatsapp_smart_followup_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("connection_id", sa.String(length=36), nullable=True),
        sa.Column("conversation_id", sa.String(length=36), nullable=True),
        sa.Column("sequence_id", sa.String(length=36), nullable=True),
        sa.Column("job_id", sa.String(length=36), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("reason_code", sa.String(length=64), nullable=True),
        sa.Column("detail", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index(
        "ix_wa_sfu_event_tenant_created",
        "whatsapp_smart_followup_events",
        ["tenant_id", "created_at"],
    )
    op.create_index("ix_wa_sfu_event_job", "whatsapp_smart_followup_events", ["job_id"])
    op.create_index("ix_wa_sfu_event_sequence", "whatsapp_smart_followup_events", ["sequence_id"])


def downgrade() -> None:
    op.drop_table("whatsapp_smart_followup_events")
    op.drop_table("whatsapp_smart_followup_jobs")
    op.drop_table("whatsapp_smart_followup_sequences")
    op.drop_table("whatsapp_smart_followup_steps")
    op.drop_table("whatsapp_smart_followup_settings")
