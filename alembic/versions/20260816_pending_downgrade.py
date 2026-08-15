"""Add pending downgrade columns to tenant_entitlements.

Revision ID: 20260816_pending_downgrade
Revises: 20260815_merge_sfu_meta_cred
Create Date: 2026-08-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260816_pending_downgrade"
down_revision: str | None = "20260815_merge_sfu_meta_cred"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tenant_entitlements",
        sa.Column("pending_plan_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "tenant_entitlements",
        sa.Column("pending_plan_effective_at", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tenant_entitlements", "pending_plan_effective_at")
    op.drop_column("tenant_entitlements", "pending_plan_id")
