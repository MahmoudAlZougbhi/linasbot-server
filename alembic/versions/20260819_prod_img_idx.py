"""AI Products — shared PostgreSQL image fingerprint index (multi-server HA)."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260819_prod_img_idx"
down_revision: str | None = "20260818_ai_services"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
    op.create_table(
        "product_image_fingerprints",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("product_id", sa.String(length=36), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_image_id", sa.String(length=36), nullable=False),
        sa.Column("media_id", sa.String(length=64), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("phash", sa.String(length=16), nullable=False),
        sa.Column("histogram", json_type, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.create_index("ix_product_img_fp_tenant_id", "product_image_fingerprints", ["tenant_id"])
    op.create_index("ix_product_img_fp_tenant_product", "product_image_fingerprints", ["tenant_id", "product_id"])
    op.create_index("ix_product_img_fp_tenant_sha256", "product_image_fingerprints", ["tenant_id", "sha256"])
    op.create_index(
        "ix_product_img_fp_tenant_media",
        "product_image_fingerprints",
        ["tenant_id", "media_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("product_image_fingerprints")
