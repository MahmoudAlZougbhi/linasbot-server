"""AI Products Phase 2 — availability, conversation context, reply-to mapping."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260818_ai_products_phase2"
down_revision: str | None = "20260817_ai_products"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("availability", sa.String(length=32), nullable=False, server_default="in_stock"),
    )
    op.create_index("ix_products_tenant_availability", "products", ["tenant_id", "availability"])

    op.create_table(
        "product_conversation_context",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("conversation_id", sa.String(length=128), nullable=False),
        sa.Column("active_product_id", sa.String(length=36), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_product_ctx_tenant_conversation",
        "product_conversation_context",
        ["tenant_id", "conversation_id"],
        unique=True,
    )

    op.create_table(
        "product_sent_messages",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("conversation_id", sa.String(length=128), nullable=False),
        sa.Column("channel", sa.String(length=64), nullable=False),
        sa.Column("sent_message_id", sa.String(length=128), nullable=False),
        sa.Column("product_id", sa.String(length=36), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_product_sent_msg_lookup",
        "product_sent_messages",
        ["tenant_id", "channel", "sent_message_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("product_sent_messages")
    op.drop_table("product_conversation_context")
    op.drop_index("ix_products_tenant_availability", table_name="products")
    op.drop_column("products", "availability")
