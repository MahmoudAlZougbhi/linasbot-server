"""Additive product description + English search-metadata columns.

Revision ID: 20260824_prod_search_meta
Revises: 20260823_tiktok_biz

Upgrade:
  - products.description (owner-written, nullable for legacy rows)
  - products.description_normalized (search helper)
  - products.ai_search_title / description / keywords / title_normalized (Luna, English)

Do NOT apply to production without owner-approved cutover. Runtime works with nulls.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260824_prod_search_meta"
down_revision: str | None = "20260823_tiktok_biz"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JsonType = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.add_column("products", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("products", sa.Column("description_normalized", sa.String(length=512), nullable=True))
    op.add_column("products", sa.Column("ai_search_title", sa.String(length=128), nullable=True))
    op.add_column("products", sa.Column("ai_search_description", sa.String(length=256), nullable=True))
    op.add_column("products", sa.Column("ai_search_title_normalized", sa.String(length=512), nullable=True))
    op.add_column("products", sa.Column("ai_search_keywords", JsonType, nullable=True))
    op.create_index("ix_products_tenant_desc_normalized", "products", ["tenant_id", "description_normalized"])
    op.create_index(
        "ix_products_tenant_ai_title_normalized",
        "products",
        ["tenant_id", "ai_search_title_normalized"],
    )


def downgrade() -> None:
    op.drop_index("ix_products_tenant_ai_title_normalized", table_name="products")
    op.drop_index("ix_products_tenant_desc_normalized", table_name="products")
    op.drop_column("products", "ai_search_keywords")
    op.drop_column("products", "ai_search_title_normalized")
    op.drop_column("products", "ai_search_description")
    op.drop_column("products", "ai_search_title")
    op.drop_column("products", "description_normalized")
    op.drop_column("products", "description")
