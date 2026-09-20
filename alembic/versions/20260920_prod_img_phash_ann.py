"""pHash 64-d ANN column + optional pgvector HNSW for product image fingerprints.

Revision ID: 20260920_prod_img_ann
Revises: 20260919_prod_img_phash
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260920_prod_img_ann"
down_revision: str | None = "20260919_prod_img_phash"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JsonType = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def _vector_available(conn: sa.Connection) -> bool:
    try:
        return bool(
            conn.execute(
                sa.text("SELECT EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'vector')")
            ).scalar()
        )
    except Exception:
        return False


def upgrade() -> None:
    op.add_column("product_image_fingerprints", sa.Column("phash_vec", JsonType, nullable=True))
    conn = op.get_bind()
    if not _vector_available(conn):
        return
    op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
    op.execute(sa.text("ALTER TABLE product_image_fingerprints ADD COLUMN IF NOT EXISTS phash_embedding vector(64)"))
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_product_img_fp_phash_ann "
            "ON product_image_fingerprints "
            "USING hnsw (phash_embedding vector_cosine_ops)"
        )
    )


def downgrade() -> None:
    conn = op.get_bind()
    if _vector_available(conn):
        op.execute(sa.text("DROP INDEX IF EXISTS ix_product_img_fp_phash_ann"))
        op.execute(sa.text("ALTER TABLE product_image_fingerprints DROP COLUMN IF EXISTS phash_embedding"))
    op.drop_column("product_image_fingerprints", "phash_vec")
