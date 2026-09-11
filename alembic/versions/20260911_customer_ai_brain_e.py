"""20260911_cust_ai_brain_e

Durable memory + rolling summaries for Customer Brain Full Agentic path.
Revision ID: 20260911_cust_ai_brain_e
Revises: 20260910_req_web_chat
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260911_cust_ai_brain_e"
down_revision: str | None = "20260910_req_web_chat"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JsonType = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "customer_ai_memory_facts",
        sa.Column("id", sa.String(length=128), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("customer_id", sa.String(length=128), nullable=False),
        sa.Column("fact_type", sa.String(length=64), nullable=False, server_default=sa.text("'preference'")),
        sa.Column("fact_key", sa.String(length=80), nullable=False),
        sa.Column("fact_value", sa.Text(), nullable=False),
        sa.Column("source_message_ids", JsonType, nullable=False, server_default=sa.text("'[]'")),
        sa.Column("confidence", sa.Float(), nullable=False, server_default=sa.text("0.7")),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'active'")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("superseded_by", sa.String(length=128), nullable=False, server_default=sa.text("''")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "customer_id", "fact_key", name="uq_customer_ai_memory_fact"),
    )
    op.create_index(
        "ix_customer_ai_memory_tenant_customer",
        "customer_ai_memory_facts",
        ["tenant_id", "customer_id", "status"],
    )

    op.create_table(
        "customer_ai_memory_summaries",
        sa.Column("id", sa.String(length=128), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("conversation_id", sa.String(length=128), nullable=False),
        sa.Column("summary_text", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("source_message_ids", JsonType, nullable=False, server_default=sa.text("'[]'")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "conversation_id", name="uq_customer_ai_memory_summary"),
    )
    op.create_index(
        "ix_customer_ai_memory_summary_tenant",
        "customer_ai_memory_summaries",
        ["tenant_id"],
    )

    # Pointer lifecycle metadata for candidate/active contextual indexes.
    op.add_column(
        "customer_ai_index_pointers",
        sa.Column("lifecycle", sa.String(length=32), nullable=False, server_default=sa.text("'ACTIVE'")),
    )
    op.add_column(
        "customer_ai_index_pointers",
        sa.Column("candidate_version", sa.String(length=64), nullable=False, server_default=sa.text("''")),
    )


def downgrade() -> None:
    op.drop_column("customer_ai_index_pointers", "candidate_version")
    op.drop_column("customer_ai_index_pointers", "lifecycle")
    op.drop_index("ix_customer_ai_memory_summary_tenant", table_name="customer_ai_memory_summaries")
    op.drop_table("customer_ai_memory_summaries")
    op.drop_index("ix_customer_ai_memory_tenant_customer", table_name="customer_ai_memory_facts")
    op.drop_table("customer_ai_memory_facts")
