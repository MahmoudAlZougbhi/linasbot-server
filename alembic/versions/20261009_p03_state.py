"""Shared tenant state tables. Old disk paths stay until flags change.

Revision ID: 20261009_p03_state
Revises: 20261009_p02_foundation
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20261009_p03_state"
down_revision: str | None = "20261009_p02_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS config_revisions (
            tenant_id TEXT NOT NULL,
            domain TEXT NOT NULL,
            revision INTEGER NOT NULL,
            updated_at DOUBLE PRECISION NOT NULL,
            PRIMARY KEY (tenant_id, domain)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cm_versions (
            tenant_id TEXT NOT NULL,
            version_id TEXT NOT NULL,
            revision INTEGER NOT NULL,
            content TEXT NOT NULL,
            checksum TEXT NOT NULL,
            created_by TEXT NOT NULL,
            created_at DOUBLE PRECISION NOT NULL,
            PRIMARY KEY (tenant_id, version_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cm_published (
            tenant_id TEXT PRIMARY KEY,
            version_id TEXT NOT NULL,
            revision INTEGER NOT NULL,
            published_at DOUBLE PRECISION NOT NULL,
            published_by TEXT NOT NULL,
            checksum TEXT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS realtime_events (
            id INTEGER PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            channel TEXT NOT NULL,
            payload TEXT NOT NULL,
            created_at DOUBLE PRECISION NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS conversations (
            tenant_id TEXT NOT NULL,
            conversation_id TEXT NOT NULL,
            channel TEXT NOT NULL,
            status TEXT NOT NULL,
            unread_count INTEGER NOT NULL DEFAULT 0,
            last_message_at DOUBLE PRECISION NOT NULL,
            PRIMARY KEY (tenant_id, conversation_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            tenant_id TEXT NOT NULL,
            conversation_id TEXT NOT NULL,
            message_id TEXT NOT NULL,
            direction TEXT NOT NULL,
            body TEXT NOT NULL,
            created_at DOUBLE PRECISION NOT NULL,
            PRIMARY KEY (tenant_id, conversation_id, message_id)
        )
        """
    )


def downgrade() -> None:
    for name in (
        "messages",
        "conversations",
        "realtime_events",
        "cm_published",
        "cm_versions",
        "config_revisions",
    ):
        op.execute(f"DROP TABLE IF EXISTS {name}")
