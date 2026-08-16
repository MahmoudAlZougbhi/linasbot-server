"""Alembic revision for request definition graphs.

Revision ID: 20260820_request_graphs
Revises: 20260817_web_chat_ha
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260820_request_graphs"
down_revision: str | None = "20260817_web_chat_ha"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "request_definition_graphs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("definition_id", sa.String(length=64), nullable=False),
        sa.Column("source_item_id", sa.String(length=128), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("source_text_hash", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("destination", sa.String(length=32), nullable=False, server_default="general"),
        sa.Column("graph_json", sa.JSON(), nullable=False),
        sa.Column("confirmation_required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("needs_owner_clarification", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_reqdef_tenant_definition", "request_definition_graphs", ["tenant_id", "definition_id"])
    op.create_index("ix_reqdef_tenant_status", "request_definition_graphs", ["tenant_id", "status"])
    op.create_unique_constraint(
        "uq_reqdef_tenant_source_rev",
        "request_definition_graphs",
        ["tenant_id", "source_item_id", "revision"],
    )
    op.create_table(
        "request_definition_links",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column(
            "graph_id",
            sa.String(length=36),
            sa.ForeignKey("request_definition_graphs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("definition_id", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=False),
    )
    op.create_index("ix_reqdef_link_tenant_def", "request_definition_links", ["tenant_id", "definition_id"])


def downgrade() -> None:
    op.drop_table("request_definition_links")
    op.drop_table("request_definition_graphs")
