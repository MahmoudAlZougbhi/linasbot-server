"""Raise product image sort_order cap from 3 to 5 (design: up to 5 images)."""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260822_product_images_max5"
down_revision: str | None = "20260821_request_drafts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_product_images_sort_order", "product_images", type_="check")
    op.create_check_constraint(
        "ck_product_images_sort_order",
        "product_images",
        "sort_order >= 0 AND sort_order < 5",
    )


def downgrade() -> None:
    op.drop_constraint("ck_product_images_sort_order", "product_images", type_="check")
    op.create_check_constraint(
        "ck_product_images_sort_order",
        "product_images",
        "sort_order >= 0 AND sort_order < 3",
    )
