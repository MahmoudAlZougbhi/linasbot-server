"""Postgres queue, dedupe, inbound events, and feature flags.

Revision ID: 20261009_p02_foundation
Revises: 20261008_portal_r3
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20261009_p02_foundation"
down_revision: str | None = "20261008_portal_r3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS platform_jobs (
            id TEXT PRIMARY KEY,
            queue TEXT NOT NULL,
            job_type TEXT NOT NULL,
            tenant_id TEXT NOT NULL,
            payload TEXT NOT NULL,
            status TEXT NOT NULL,
            idempotency_key TEXT,
            attempts INTEGER NOT NULL DEFAULT 0,
            max_attempts INTEGER NOT NULL DEFAULT 5,
            run_after DOUBLE PRECISION NOT NULL,
            lease_until DOUBLE PRECISION,
            lease_owner TEXT,
            last_error TEXT,
            created_at DOUBLE PRECISION NOT NULL,
            updated_at DOUBLE PRECISION NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_platform_jobs_idem
        ON platform_jobs (queue, idempotency_key)
        WHERE idempotency_key IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS platform_job_dlq (
            id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL,
            queue TEXT NOT NULL,
            tenant_id TEXT NOT NULL,
            payload TEXT NOT NULL,
            reason TEXT NOT NULL,
            attempts INTEGER NOT NULL,
            created_at DOUBLE PRECISION NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS outbound_deliveries (
            idempotency_key TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            provider TEXT NOT NULL,
            provider_message_id TEXT,
            created_at DOUBLE PRECISION NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS inbound_events (
            provider TEXT NOT NULL,
            provider_event_id TEXT NOT NULL,
            tenant_id TEXT NOT NULL,
            payload TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at DOUBLE PRECISION NOT NULL,
            PRIMARY KEY (provider, provider_event_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS feature_flags (
            flag_key TEXT NOT NULL,
            scope TEXT NOT NULL,
            scope_id TEXT NOT NULL DEFAULT '',
            value TEXT NOT NULL,
            updated_by TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (flag_key, scope, scope_id)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS feature_flags")
    op.execute("DROP TABLE IF EXISTS inbound_events")
    op.execute("DROP TABLE IF EXISTS outbound_deliveries")
    op.execute("DROP TABLE IF EXISTS platform_job_dlq")
    op.execute("DROP INDEX IF EXISTS ux_platform_jobs_idem")
    op.execute("DROP TABLE IF EXISTS platform_jobs")
