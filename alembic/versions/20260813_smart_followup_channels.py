"""Add channel routing columns to Smart Follow-Up sequences/jobs."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "20260813_smart_followup_channels"
down_revision: str | None = "20260812_outbox_claim_lease"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "whatsapp_smart_followup_sequences",
        sa.Column("channel", sa.String(length=32), nullable=False, server_default="whatsapp_cloud"),
    )
    op.add_column(
        "whatsapp_smart_followup_sequences",
        sa.Column("channel_context", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.add_column(
        "whatsapp_smart_followup_jobs",
        sa.Column("channel", sa.String(length=32), nullable=False, server_default="whatsapp_cloud"),
    )
    op.add_column(
        "whatsapp_smart_followup_jobs",
        sa.Column("channel_context", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.create_index("ix_wa_sfu_job_channel", "whatsapp_smart_followup_jobs", ["channel", "status"])


def downgrade() -> None:
    op.drop_index("ix_wa_sfu_job_channel", table_name="whatsapp_smart_followup_jobs")
    op.drop_column("whatsapp_smart_followup_jobs", "channel_context")
    op.drop_column("whatsapp_smart_followup_jobs", "channel")
    op.drop_column("whatsapp_smart_followup_sequences", "channel_context")
    op.drop_column("whatsapp_smart_followup_sequences", "channel")
