"""Store WhatsApp Call intent on the Cloud connection (default off).

Revision ID: 20260908_wa_calls_enabled
Revises: 20260907_tiktok_enhanced
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260908_wa_calls_enabled"
down_revision: str | None = "20260907_tiktok_enhanced"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "whatsapp_connections",
        sa.Column("calls_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("whatsapp_connections", "calls_enabled")
