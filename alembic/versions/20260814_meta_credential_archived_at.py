"""Add archived_at to meta_binding_credentials (soft disconnect archive).

Revision ID: 20260814_meta_credential_archived_at
Revises: 20260814_widen_ver_num
Create Date: 2026-08-14

Additive column only. Credentials with archived_at > 0 are retained for audit but
must not be used for webhook or Graph calls after owner disconnect.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260814_meta_credential_archived_at"
down_revision: str | None = "20260814_widen_ver_num"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "meta_binding_credentials",
        sa.Column("archived_at", sa.Float(), nullable=False, server_default=sa.text("0")),
    )


def downgrade() -> None:
    op.drop_column("meta_binding_credentials", "archived_at")
