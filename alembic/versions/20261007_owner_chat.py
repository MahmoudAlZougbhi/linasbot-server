"""Shared owner copilot conversations.

Revision ID: 20261007_owner_chat
Revises: 20261007_owner_portal
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20261007_owner_chat"
down_revision: str | None = "20261007_owner_portal"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS owner_copilot_conversations (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL DEFAULT '',
            user_id TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL DEFAULT '',
            created_at DOUBLE PRECISION NOT NULL DEFAULT 0,
            updated_at DOUBLE PRECISION NOT NULL DEFAULT 0,
            archived INTEGER NOT NULL DEFAULT 0,
            deleted INTEGER NOT NULL DEFAULT 0,
            payload TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_owner_copilot_conversations_user
        ON owner_copilot_conversations (tenant_id, user_id)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_owner_copilot_conversations_user")
    op.execute("DROP TABLE IF EXISTS owner_copilot_conversations")
