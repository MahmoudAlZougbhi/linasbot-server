"""Persist Meta comment permission verification on asset bindings.

Revision ID: 20260826_meta_comment_perm
Revises: 20260825_tenant_runtime_cfg
Create Date: 2026-08-26

Upgrade:
  - Adds comment_permission_* columns on meta_asset_bindings.
  - Defaults to unknown; runtime/bootstrap migrates verified state from stored credentials.

Rollback:
  - Drops the new columns (verification state is re-derived on re-upgrade).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260826_meta_comment_perm"
down_revision: str | None = "20260825_tenant_runtime_cfg"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "meta_asset_bindings",
        sa.Column(
            "comment_permission_status",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'unknown'"),
        ),
    )
    op.add_column(
        "meta_asset_bindings",
        sa.Column(
            "comment_permission_verified_at",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "meta_asset_bindings",
        sa.Column(
            "comment_permission_source",
            sa.String(length=64),
            nullable=False,
            server_default=sa.text("''"),
        ),
    )
    op.add_column(
        "meta_asset_bindings",
        sa.Column(
            "comment_permission_credential_id",
            sa.String(length=64),
            nullable=False,
            server_default=sa.text("''"),
        ),
    )
    op.add_column(
        "meta_asset_bindings",
        sa.Column(
            "comment_permission_token_fingerprint",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("''"),
        ),
    )


def downgrade() -> None:
    op.drop_column("meta_asset_bindings", "comment_permission_token_fingerprint")
    op.drop_column("meta_asset_bindings", "comment_permission_credential_id")
    op.drop_column("meta_asset_bindings", "comment_permission_source")
    op.drop_column("meta_asset_bindings", "comment_permission_verified_at")
    op.drop_column("meta_asset_bindings", "comment_permission_status")
