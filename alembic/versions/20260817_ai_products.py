"""AI Products catalog tables (additive, tenant-scoped).

Revision ID: 20260817_ai_products
Revises: 20260816_pending_downgrade
Create Date: 2026-08-17

Upgrade:
  - products, product_images, product_links for tenant-isolated catalog CRUD.
  - Image binaries stay on disk; DB stores metadata only.
  - Additive only; safe for existing tenants (empty tables).

Do NOT apply to production without owner-approved cutover.

Rollback:
  - downgrade() drops tables in FK-safe order.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260817_ai_products"
down_revision: str | None = "20260816_pending_downgrade"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JsonType = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=512), nullable=False),
        sa.Column("name_normalized", sa.String(length=512), nullable=False),
        sa.Column("price", sa.String(length=128), nullable=True),
        sa.Column("sizes", JsonType, nullable=True),
        sa.Column("colors", JsonType, nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.create_index("ix_products_tenant_id", "products", ["tenant_id"])
    op.create_index(
        "ix_products_tenant_updated",
        "products",
        ["tenant_id", "updated_at"],
    )
    op.create_index(
        "ix_products_tenant_name_normalized",
        "products",
        ["tenant_id", "name_normalized"],
    )

    op.create_table(
        "product_images",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column(
            "product_id",
            sa.String(length=36),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("media_id", sa.String(length=64), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("sort_order >= 0 AND sort_order < 3", name="ck_product_images_sort_order"),
    )
    op.create_index("ix_product_images_tenant_id", "product_images", ["tenant_id"])
    op.create_index("ix_product_images_product_id", "product_images", ["product_id"])
    op.create_index(
        "ix_product_images_tenant_media",
        "product_images",
        ["tenant_id", "media_id"],
    )

    op.create_table(
        "product_links",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column(
            "product_id",
            sa.String(length=36),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("label", sa.String(length=256), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.create_index("ix_product_links_tenant_id", "product_links", ["tenant_id"])
    op.create_index("ix_product_links_product_id", "product_links", ["product_id"])


def downgrade() -> None:
    op.drop_table("product_links")
    op.drop_table("product_images")
    op.drop_table("products")
