"""Owner archive flag, embed retry queue, Voyage counts, and orphan-vector purge.

Revision ID: 20261008_portal_r3
Revises: 20261008_portal_r2
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20261008_portal_r3"
down_revision: str | None = "20261008_portal_r2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE owner_portal_tenant_visibility ADD COLUMN IF NOT EXISTS archived INTEGER NOT NULL DEFAULT 0"
    )
    op.execute("ALTER TABLE owner_portal_tenant_visibility ADD COLUMN IF NOT EXISTS email TEXT NOT NULL DEFAULT ''")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS owner_portal_embed_jobs (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            ref_id TEXT NOT NULL,
            payload TEXT NOT NULL DEFAULT '{}',
            attempts INTEGER NOT NULL DEFAULT 0,
            next_at TEXT NOT NULL DEFAULT ''
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_owner_embed_jobs_next ON owner_portal_embed_jobs (next_at)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS owner_portal_voyage_events (
            id BIGSERIAL PRIMARY KEY,
            feature TEXT NOT NULL,
            status INTEGER NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_owner_voyage_events_created ON owner_portal_voyage_events (created_at)")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_search_docs_family_parent
        ON customer_ai_search_documents (source_family, parent_id)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS owner_portal_orphan_vector_backup AS
        SELECT * FROM customer_ai_search_documents WHERE false
        """
    )
    op.execute(
        """
        INSERT INTO owner_portal_orphan_vector_backup
        SELECT d.* FROM customer_ai_search_documents d
        WHERE d.source_family = 'owner_kb'
          AND NOT EXISTS (
              SELECT 1 FROM owner_copilot_kb_entries e
              WHERE e.id = d.parent_id OR e.id = d.source_id
          )
          AND NOT EXISTS (
              SELECT 1 FROM owner_portal_orphan_vector_backup b WHERE b.id = d.id
          )
        """
    )
    op.execute(
        """
        INSERT INTO owner_portal_orphan_vector_backup
        SELECT d.* FROM customer_ai_search_documents d
        WHERE d.source_family = 'owner_qa'
          AND NOT EXISTS (
              SELECT 1 FROM owner_copilot_qa q WHERE q.id = d.parent_id
          )
          AND NOT EXISTS (
              SELECT 1 FROM owner_portal_orphan_vector_backup b WHERE b.id = d.id
          )
        """
    )
    op.execute(
        """
        DELETE FROM customer_ai_search_documents d
        WHERE d.source_family = 'owner_kb'
          AND NOT EXISTS (
              SELECT 1 FROM owner_copilot_kb_entries e
              WHERE e.id = d.parent_id OR e.id = d.source_id
          )
        """
    )
    op.execute(
        """
        DELETE FROM customer_ai_search_documents d
        WHERE d.source_family = 'owner_qa'
          AND NOT EXISTS (
              SELECT 1 FROM owner_copilot_qa q WHERE q.id = d.parent_id
          )
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_search_docs_family_parent")
    op.execute("DROP TABLE IF EXISTS owner_portal_orphan_vector_backup")
    op.execute("DROP INDEX IF EXISTS ix_owner_voyage_events_created")
    op.execute("DROP TABLE IF EXISTS owner_portal_voyage_events")
    op.execute("DROP INDEX IF EXISTS ix_owner_embed_jobs_next")
    op.execute("DROP TABLE IF EXISTS owner_portal_embed_jobs")
    op.execute("ALTER TABLE owner_portal_tenant_visibility DROP COLUMN IF EXISTS email")
    op.execute("ALTER TABLE owner_portal_tenant_visibility DROP COLUMN IF EXISTS archived")
