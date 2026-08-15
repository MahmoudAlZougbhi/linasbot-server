"""Website Chat HA tables for visitor sessions, messages, delivery, widgets, and operations FSM.

Revision ID: 20260817_web_chat_ha
Revises: 20260816_pending_downgrade
Create Date: 2026-08-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260817_web_chat_ha"
down_revision: str | None = "20260819_prod_img_idx"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JsonType = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "web_chat_visitor_sessions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("session_id", sa.String(length=80), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("widget_key", sa.String(length=120), nullable=False),
        sa.Column("authority_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("session_id", name="uq_web_chat_visitor_sessions_session_id"),
    )
    op.create_index(
        "ix_web_chat_visitor_sessions_tenant_widget",
        "web_chat_visitor_sessions",
        ["tenant_id", "widget_key"],
    )

    op.create_table(
        "web_chat_messages",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("session_id", sa.String(length=80), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("message_id", sa.String(length=120), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("acked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("meta", JsonType, nullable=True),
        sa.UniqueConstraint("session_id", "message_id", name="uq_web_chat_messages_session_message"),
    )
    op.create_index(
        "ix_web_chat_messages_session_created",
        "web_chat_messages",
        ["session_id", "created_at"],
    )

    op.create_table(
        "web_chat_delivery_idempotency",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=80), nullable=False),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("message_id", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_web_chat_delivery_idempotency"),
    )

    op.create_table(
        "web_chat_widgets",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("widget_key", sa.String(length=120), nullable=False),
        sa.Column("config", JsonType, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", name="uq_web_chat_widgets_tenant_id"),
        sa.UniqueConstraint("widget_key", name="uq_web_chat_widgets_widget_key"),
    )

    op.create_table(
        "web_chat_operations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=80), nullable=False),
        sa.Column("operation_key", sa.String(length=200), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("lease_owner", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("lease_generation", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reservation_id", sa.String(length=64), nullable=True),
        sa.Column("released", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("result", JsonType, nullable=True),
        sa.Column("snapshot", JsonType, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "operation_key", name="uq_web_chat_operations_tenant_key"),
    )
    op.create_index("ix_web_chat_operations_state", "web_chat_operations", ["state"])
    op.create_index("ix_web_chat_operations_session", "web_chat_operations", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_web_chat_operations_session", table_name="web_chat_operations")
    op.drop_index("ix_web_chat_operations_state", table_name="web_chat_operations")
    op.drop_table("web_chat_operations")
    op.drop_table("web_chat_widgets")
    op.drop_table("web_chat_delivery_idempotency")
    op.drop_table("web_chat_messages")
    op.drop_index("ix_web_chat_visitor_sessions_tenant_widget", table_name="web_chat_visitor_sessions")
    op.drop_table("web_chat_visitor_sessions")
