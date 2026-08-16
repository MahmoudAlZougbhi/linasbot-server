"""Alembic revision for customer request drafts.

Revision ID: 20260821_request_drafts
Revises: 20260820_request_graphs
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260821_request_drafts"
down_revision: str | None = "20260820_request_graphs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "customer_request_drafts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("draft_id", sa.String(length=64), nullable=False),
        sa.Column("customer_id", sa.String(length=128), nullable=False),
        sa.Column("conversation_id", sa.String(length=128), nullable=True),
        sa.Column("definition_id", sa.String(length=64), nullable=False),
        sa.Column("definition_revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("destination", sa.String(length=32), nullable=False, server_default="general"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="collecting"),
        sa.Column("values_json", sa.JSON(), nullable=False),
        sa.Column("missing_json", sa.JSON(), nullable=False),
        sa.Column("items_json", sa.JSON(), nullable=False),
        sa.Column("linked_entities_json", sa.JSON(), nullable=False),
        sa.Column("last_idempotency", sa.String(length=64), nullable=True),
        sa.Column("submitted_request_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_reqdraft_tenant_customer_status",
        "customer_request_drafts",
        ["tenant_id", "customer_id", "status"],
    )
    op.create_index("ix_reqdraft_tenant_definition", "customer_request_drafts", ["tenant_id", "definition_id"])
    op.create_unique_constraint("uq_reqdraft_tenant_draft", "customer_request_drafts", ["tenant_id", "draft_id"])


def downgrade() -> None:
    op.drop_table("customer_request_drafts")
