"""Add connection_source for temporary Meta App Review WhatsApp binds.

Revision ID: 20260811_wa_app_review_source
Revises: 20260811_whatsapp_smart_followup
Create Date: 2026-08-11

Upgrade (PostgreSQL production SoT):
  - Adds non-null connection_source with server_default 'embedded_signup'
    so existing Embedded Signup rows remain valid without backfill SQL.
  - Adds check constraint + index. Additive only; no data rewrite.
  - Uses batch_alter_table so local SQLite verification matches PG shape.

Rollback strategy:
  - downgrade() drops the index, check constraint, then the column.
  - Safe only when no active meta_app_review_test rows are required;
    temporary App Review binds must be unbound before intentional rollback.
  - Does not touch credentials, messages, audits, or Embedded Signup rows
    beyond removing the provenance column (values discarded).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260811_wa_app_review_source"
down_revision: str | None = "20260811_whatsapp_smart_followup"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("whatsapp_connections") as batch_op:
        batch_op.add_column(
            sa.Column(
                "connection_source",
                sa.String(length=64),
                nullable=False,
                server_default="embedded_signup",
            )
        )
        batch_op.create_check_constraint(
            "ck_wa_connection_source",
            "connection_source IN ('embedded_signup','meta_app_review_test')",
        )
        batch_op.create_index("ix_wa_connection_source", ["connection_source"])


def downgrade() -> None:
    with op.batch_alter_table("whatsapp_connections") as batch_op:
        batch_op.drop_index("ix_wa_connection_source")
        batch_op.drop_constraint("ck_wa_connection_source", type_="check")
        batch_op.drop_column("connection_source")
