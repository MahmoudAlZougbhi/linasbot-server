"""Add claimed_at lease column for outbox crash reclaim.

Revision ID: 20260812_outbox_claim_lease
Revises: 20260812_outbox_processing
Create Date: 2026-08-12

Upgrade:
  - customer_request_outbox.claimed_at for stale processing reclaim.

Do NOT apply Requests migrations to production without owner approval.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260812_outbox_claim_lease"
down_revision: str | None = "20260812_outbox_processing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "customer_request_outbox",
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_customer_request_outbox_status_claimed",
        "customer_request_outbox",
        ["status", "claimed_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_customer_request_outbox_status_claimed", table_name="customer_request_outbox")
    op.drop_column("customer_request_outbox", "claimed_at")
