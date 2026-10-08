"""Shared owner audit, activity flow, and an omnichannel time index.

Revision ID: 20261008_portal_r2
Revises: 20261007_owner_chat
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20261008_portal_r2"
down_revision: str | None = "20261007_owner_chat"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS owner_portal_audit_events (
            id TEXT PRIMARY KEY,
            actor_user_id TEXT NOT NULL DEFAULT '',
            action TEXT NOT NULL DEFAULT '',
            tenant_id TEXT NOT NULL DEFAULT '',
            details TEXT NOT NULL DEFAULT '{}',
            created_at DOUBLE PRECISION NOT NULL DEFAULT 0
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_owner_portal_audit_created ON owner_portal_audit_events (created_at)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS owner_portal_flow_events (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL DEFAULT '',
            channel TEXT NOT NULL DEFAULT '',
            message_type TEXT NOT NULL DEFAULT 'text',
            created_at TEXT NOT NULL DEFAULT '',
            payload TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_owner_portal_flow_tenant_created
        ON owner_portal_flow_events (tenant_id, created_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_omni_inbound_created
        ON omnichannel_inbound_events (created_at)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS owner_portal_tenant_visibility (
            tenant_id TEXT PRIMARY KEY,
            hidden INTEGER NOT NULL,
            updated_at TEXT NOT NULL DEFAULT ''
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS owner_portal_tenant_visibility")
    op.execute("DROP INDEX IF EXISTS ix_omni_inbound_created")
    op.execute("DROP INDEX IF EXISTS ix_owner_portal_flow_tenant_created")
    op.execute("DROP TABLE IF EXISTS owner_portal_flow_events")
    op.execute("DROP INDEX IF EXISTS ix_owner_portal_audit_created")
    op.execute("DROP TABLE IF EXISTS owner_portal_audit_events")
