"""Tenant services + priced options (additive, tenant-scoped).

Revision ID: 20260818_ai_services
Revises: 20260817_ai_products
Create Date: 2026-08-18

Upgrade:
  - services, service_options for tenant-isolated service pricing CRUD.
  - Additive only; safe for existing tenants (empty tables).

Do NOT apply to production without owner-approved cutover.

Rollback:
  - downgrade() drops tables in FK-safe order.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260818_ai_services"
down_revision: str | None = "20260817_ai_products"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "services",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=512), nullable=False),
        sa.Column("name_normalized", sa.String(length=512), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
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
    op.create_index("ix_services_tenant_id", "services", ["tenant_id"])
    op.create_index("ix_services_tenant_updated", "services", ["tenant_id", "updated_at"])
    op.create_index(
        "ix_services_tenant_name_normalized",
        "services",
        ["tenant_id", "name_normalized"],
    )

    op.create_table(
        "service_options",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column(
            "service_id",
            sa.String(length=36),
            sa.ForeignKey("services.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("machine_name", sa.String(length=256), nullable=True),
        sa.Column("body_part", sa.String(length=256), nullable=True),
        sa.Column("staff_name", sa.String(length=256), nullable=True),
        sa.Column("price", sa.String(length=128), nullable=False),
        sa.Column("currency", sa.String(length=16), nullable=False, server_default=sa.text("'USD'")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.create_index("ix_service_options_tenant_id", "service_options", ["tenant_id"])
    op.create_index("ix_service_options_service_id", "service_options", ["service_id"])
    op.create_index(
        "ix_service_options_service_sort",
        "service_options",
        ["service_id", "sort_order"],
    )


def downgrade() -> None:
    op.drop_table("service_options")
    op.drop_table("services")
