"""TikTok enhanced post-context: token kinds + identity/advertiser binding.

Revision ID: 20260907_tiktok_enhanced
Revises: 20260826_omnichannel_rel
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260907_tiktok_enhanced"
down_revision: str | None = "20260826_omnichannel_rel"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JsonType = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.add_column(
        "tiktok_credentials",
        sa.Column("token_kind", sa.String(length=32), nullable=False, server_default="account_holder"),
    )
    op.create_check_constraint(
        "ck_tt_credential_token_kind",
        "tiktok_credentials",
        "token_kind IN ('account_holder','advertiser')",
    )
    op.create_table(
        "tiktok_enhanced_bindings",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("connection_id", sa.String(length=36), nullable=False),
        sa.Column("advertiser_credential_id", sa.String(length=36), nullable=True),
        sa.Column("advertiser_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("bc_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("identity_id", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("identity_type", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("identity_authorized_bc_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=64), nullable=False, server_default="authorization_required"),
        sa.Column("reason_code", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("capabilities", JsonType, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("last_probe_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("probe_cooldown_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_probe_code", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["connection_id"], ["tiktok_connections.id"]),
        sa.UniqueConstraint("connection_id", name="uq_tt_enhanced_connection"),
        sa.CheckConstraint(
            "status IN ("
            "'waiting_for_permission','authorization_required','identity_authorization_required',"
            "'reauthorization_required','active','limited','error','disconnected'"
            ")",
            name="ck_tt_enhanced_status",
        ),
    )
    op.create_index("ix_tt_enhanced_tenant", "tiktok_enhanced_bindings", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_tt_enhanced_tenant", table_name="tiktok_enhanced_bindings")
    op.drop_table("tiktok_enhanced_bindings")
    op.drop_constraint("ck_tt_credential_token_kind", "tiktok_credentials", type_="check")
    op.drop_column("tiktok_credentials", "token_kind")
