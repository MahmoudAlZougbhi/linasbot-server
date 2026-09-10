"""Customer Brain search documents + publication pointers.

Revision ID: 20260910_cust_ai_search
Revises: 20260908_wa_calls_enabled

Creates tenant-scoped search metadata. Vector column is added only when the
pgvector extension is available. Missing extension is a typed readiness miss,
not a fake semantic index.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260910_cust_ai_search"
down_revision: str | None = "20260908_wa_calls_enabled"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JsonType = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def _vector_available(conn: sa.Connection) -> bool:
    try:
        return bool(
            conn.execute(
                sa.text("SELECT EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'vector')")
            ).scalar()
        )
    except Exception:
        return False


def upgrade() -> None:
    conn = op.get_bind()
    has_vector = _vector_available(conn)
    if has_vector:
        op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))

    op.create_table(
        "customer_ai_index_pointers",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("space_id", sa.String(length=255), nullable=False),
        sa.Column("source_family", sa.String(length=32), nullable=False),
        sa.Column("active_version", sa.String(length=64), nullable=False, server_default=sa.text("''")),
        sa.Column("rollback_version", sa.String(length=64), nullable=False, server_default=sa.text("''")),
        sa.Column("ready", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("reason", sa.String(length=64), nullable=False, server_default=sa.text("'index_not_ready'")),
        sa.Column("source_revision", sa.String(length=128), nullable=False, server_default=sa.text("''")),
        sa.Column("record_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "space_id", "source_family", name="uq_customer_ai_index_pointer"),
    )
    op.create_index("ix_customer_ai_index_tenant", "customer_ai_index_pointers", ["tenant_id"])

    op.create_table(
        "customer_ai_search_documents",
        sa.Column("id", sa.String(length=128), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("space_id", sa.String(length=255), nullable=False),
        sa.Column("source_family", sa.String(length=32), nullable=False),
        sa.Column("source_id", sa.String(length=128), nullable=False),
        sa.Column("chunk_id", sa.String(length=128), nullable=False, server_default=sa.text("''")),
        sa.Column("parent_id", sa.String(length=128), nullable=False, server_default=sa.text("''")),
        sa.Column("index_version", sa.String(length=64), nullable=False),
        sa.Column("source_revision", sa.String(length=128), nullable=False, server_default=sa.text("''")),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=False, server_default=sa.text("''")),
        sa.Column("title", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("search_text", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("visible", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("payload", JsonType, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "tenant_id",
            "space_id",
            "source_id",
            "chunk_id",
            "index_version",
            name="uq_customer_ai_search_doc",
        ),
    )
    op.create_index(
        "ix_customer_ai_search_tenant_family",
        "customer_ai_search_documents",
        ["tenant_id", "source_family", "visible"],
    )
    op.create_index(
        "ix_customer_ai_search_source",
        "customer_ai_search_documents",
        ["tenant_id", "source_id"],
    )
    if has_vector:
        op.execute(
            sa.text(
                "ALTER TABLE customer_ai_search_documents "
                "ADD COLUMN IF NOT EXISTS embedding vector(1024)"
            )
        )


def downgrade() -> None:
    op.drop_index("ix_customer_ai_search_source", table_name="customer_ai_search_documents")
    op.drop_index("ix_customer_ai_search_tenant_family", table_name="customer_ai_search_documents")
    op.drop_table("customer_ai_search_documents")
    op.drop_index("ix_customer_ai_index_tenant", table_name="customer_ai_index_pointers")
    op.drop_table("customer_ai_index_pointers")
