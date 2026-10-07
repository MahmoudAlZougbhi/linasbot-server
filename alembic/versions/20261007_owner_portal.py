"""Owner portal knowledge, Q&A, and message traces.

Revision ID: 20261007_owner_portal
Revises: 20261006_staff_alerts
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20261007_owner_portal"
down_revision: str | None = "20261006_staff_alerts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS owner_copilot_kb_entries (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL DEFAULT '',
            body TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT ''
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS owner_copilot_qa (
            id TEXT PRIMARY KEY,
            source_language TEXT NOT NULL DEFAULT 'en',
            created_at TEXT NOT NULL DEFAULT ''
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS owner_copilot_qa_variants (
            qa_id TEXT NOT NULL,
            language TEXT NOT NULL,
            question TEXT NOT NULL DEFAULT '',
            answer TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (qa_id, language)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS owner_message_traces (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL DEFAULT '',
            brain TEXT NOT NULL DEFAULT '',
            channel TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT '',
            has_error INTEGER NOT NULL DEFAULT 0,
            tokens_in INTEGER NOT NULL DEFAULT 0,
            tokens_out INTEGER NOT NULL DEFAULT 0,
            cost_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
            payload TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_owner_message_traces_created
        ON owner_message_traces (created_at)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_owner_message_traces_created")
    op.execute("DROP TABLE IF EXISTS owner_message_traces")
    op.execute("DROP TABLE IF EXISTS owner_copilot_qa_variants")
    op.execute("DROP TABLE IF EXISTS owner_copilot_qa")
    op.execute("DROP TABLE IF EXISTS owner_copilot_kb_entries")
