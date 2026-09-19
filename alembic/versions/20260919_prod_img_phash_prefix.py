"""pHash prefix index for product image candidate cut (not million-row HNSW).

Revision ID: 20260919_prod_img_phash
Revises: 20260918_widen_provider_ids
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260919_prod_img_phash"
down_revision: str | None = "20260918_widen_provider_ids"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_product_img_fp_tenant_phash",
        "product_image_fingerprints",
        ["tenant_id", "phash"],
    )


def downgrade() -> None:
    op.drop_index("ix_product_img_fp_tenant_phash", table_name="product_image_fingerprints")
