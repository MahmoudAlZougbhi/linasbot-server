"""20260912_cai_tidx

Durable per-tenant Customer Brain index lifecycle (NO_INDEX→…→ACTIVE).
Revision ID: 20260912_cai_tidx
Revises: 20260911_cust_ai_brain_e
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260912_cai_tidx"
down_revision: str | None = "20260911_cust_ai_brain_e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "customer_ai_tenant_index",
        sa.Column("tenant_id", sa.String(length=64), primary_key=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'NO_INDEX'")),
        sa.Column("content_revision", sa.String(length=128), nullable=False, server_default=sa.text("''")),
        sa.Column("active_version", sa.String(length=128), nullable=False, server_default=sa.text("''")),
        sa.Column("candidate_version", sa.String(length=128), nullable=False, server_default=sa.text("''")),
        sa.Column("rollback_version", sa.String(length=128), nullable=False, server_default=sa.text("''")),
        sa.Column("embedding_model", sa.String(length=64), nullable=False, server_default=sa.text("''")),
        sa.Column("contextual_model", sa.String(length=64), nullable=False, server_default=sa.text("''")),
        sa.Column("contextualization_version", sa.String(length=64), nullable=False, server_default=sa.text("''")),
        sa.Column("chunker_version", sa.String(length=64), nullable=False, server_default=sa.text("''")),
        sa.Column("compiler_version", sa.String(length=64), nullable=False, server_default=sa.text("''")),
        sa.Column("failure_reason", sa.String(length=240), nullable=False, server_default=sa.text("''")),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_customer_ai_tenant_index_status", "customer_ai_tenant_index", ["status"])


def downgrade() -> None:
    op.drop_index("ix_customer_ai_tenant_index_status", table_name="customer_ai_tenant_index")
    op.drop_table("customer_ai_tenant_index")
