"""Tenant runtime configuration Postgres SoT (HA shared state).

Revision ID: 20260825_tenant_runtime_cfg
Revises: 20260824_prod_search_meta
Create Date: 2026-08-25

Additive tables for channel toggles, per-asset comment settings, CM draft/published
metadata, and comment-sync cursors. Legacy node-local files remain as caches.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260825_tenant_runtime_cfg"
down_revision: str | None = "20260824_prod_search_meta"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JsonType = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "tenant_cm_draft_sections",
        sa.Column("tenant_id", sa.String(length=64), primary_key=True),
        sa.Column("section", sa.String(length=64), primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("etag", sa.String(length=128), nullable=False, server_default=sa.text("''")),
        sa.Column("payload", JsonType, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("updated_by", sa.String(length=128), nullable=False, server_default=sa.text("''")),
        sa.Column("updated_at", sa.Float(), nullable=False, server_default=sa.text("0")),
    )
    op.create_index("ix_tenant_cm_draft_sections_tenant", "tenant_cm_draft_sections", ["tenant_id"])

    op.create_table(
        "tenant_cm_published_state",
        sa.Column("tenant_id", sa.String(length=64), primary_key=True),
        sa.Column("content_version_id", sa.String(length=64), nullable=False, server_default=sa.text("''")),
        sa.Column("index_version_id", sa.String(length=64), nullable=False, server_default=sa.text("''")),
        sa.Column("checksums", JsonType, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("actions_payload", JsonType, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("embedding_provider", sa.String(length=64), nullable=False, server_default=sa.text("''")),
        sa.Column("embedding_model", sa.String(length=128), nullable=False, server_default=sa.text("''")),
        sa.Column("embedding_dimensions", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("embedding_version", sa.String(length=32), nullable=False, server_default=sa.text("''")),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("revision", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("published_at", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("updated_at", sa.Float(), nullable=False, server_default=sa.text("0")),
    )

    op.create_table(
        "tenant_meta_comment_asset_settings",
        sa.Column("tenant_id", sa.String(length=64), primary_key=True),
        sa.Column("asset_key", sa.String(length=256), primary_key=True),
        sa.Column("app_key", sa.String(length=64), nullable=False, server_default=sa.text("''")),
        sa.Column("channel", sa.String(length=32), nullable=False, server_default=sa.text("''")),
        sa.Column("asset_id", sa.String(length=128), nullable=False, server_default=sa.text("''")),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("instructions", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("revision", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("updated_at", sa.Float(), nullable=False, server_default=sa.text("0")),
    )
    op.create_index(
        "ix_tenant_meta_comment_asset_tenant",
        "tenant_meta_comment_asset_settings",
        ["tenant_id"],
    )

    op.create_table(
        "meta_comment_sync_cursors",
        sa.Column("binding_id", sa.String(length=64), primary_key=True),
        sa.Column("cursor_key", sa.String(length=128), primary_key=True),
        sa.Column("cursor_value", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("revision", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("updated_at", sa.Float(), nullable=False, server_default=sa.text("0")),
    )

    op.create_table(
        "tenant_runtime_config_migrations",
        sa.Column("tenant_id", sa.String(length=64), primary_key=True),
        sa.Column("migration_id", sa.String(length=128), primary_key=True),
        sa.Column("applied_at", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("audit", JsonType, nullable=False, server_default=sa.text("'{}'")),
    )


def downgrade() -> None:
    op.drop_table("tenant_runtime_config_migrations")
    op.drop_table("meta_comment_sync_cursors")
    op.drop_index("ix_tenant_meta_comment_asset_tenant", table_name="tenant_meta_comment_asset_settings")
    op.drop_table("tenant_meta_comment_asset_settings")
    op.drop_table("tenant_cm_published_state")
    op.drop_index("ix_tenant_cm_draft_sections_tenant", table_name="tenant_cm_draft_sections")
    op.drop_table("tenant_cm_draft_sections")
