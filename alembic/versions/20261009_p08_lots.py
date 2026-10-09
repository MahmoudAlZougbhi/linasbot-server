"""Plan lots can expire at the membership period end.

Revision ID: 20261009_p08_lots
Revises: 20261009_p03_state
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20261009_p08_lots"
down_revision: str | None = "20261009_p03_state"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("ALTER TABLE customer_ai_message_lots ADD COLUMN IF NOT EXISTS period_start TIMESTAMPTZ")
    op.execute("ALTER TABLE customer_ai_message_lots ADD COLUMN IF NOT EXISTS period_end TIMESTAMPTZ")
    op.execute("ALTER TABLE customer_ai_message_lots ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ")


def downgrade() -> None:
    return
