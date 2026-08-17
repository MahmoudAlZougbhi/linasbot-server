"""TikTok Business multi-tenant tables.

Revision ID: 20260823_tiktok_biz
Revises: 20260822_product_images_max5
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260823_tiktok_biz"
down_revision: str | None = "20260822_product_images_max5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tiktok_oauth_attempts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("state_hash", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("actor_user_id", sa.String(length=128), nullable=False),
        sa.Column("return_surface", sa.String(length=16), nullable=False),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome_code", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("state_hash", name="uq_tt_oauth_state_hash"),
        sa.CheckConstraint(
            "status IN ('pending','consumed','expired','cancelled','failed')", name="ck_tt_oauth_status"
        ),
        sa.CheckConstraint("return_surface IN ('mobile','web')", name="ck_tt_oauth_surface"),
    )
    op.create_index("ix_tt_oauth_tenant_status", "tiktok_oauth_attempts", ["tenant_id", "status"])
    op.create_index("ix_tiktok_oauth_attempts_tenant_id", "tiktok_oauth_attempts", ["tenant_id"])
    op.create_index("ix_tiktok_oauth_attempts_correlation_id", "tiktok_oauth_attempts", ["correlation_id"])

    op.create_table(
        "tiktok_connections",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=128), nullable=False),
        sa.Column("authorized_by_user_id", sa.String(length=128), nullable=False),
        sa.Column("open_id", sa.String(length=128), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("username", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("avatar_url", sa.String(length=1024), nullable=False, server_default=""),
        sa.Column("granted_scopes", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("lifecycle_status", sa.String(length=32), nullable=False, server_default="connecting"),
        sa.Column("credential_id", sa.String(length=36), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=255), nullable=True),
        sa.Column("comments_capability", sa.String(length=32), nullable=False, server_default="disconnected"),
        sa.Column("dm_capability", sa.String(length=32), nullable=False, server_default="permission_pending"),
        sa.Column("webhook_status", sa.String(length=32), nullable=False, server_default="unregistered"),
        sa.Column("sync_lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sync_lease_owner", sa.String(length=64), nullable=True),
        sa.Column("sync_cursor", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("previous_connection_id", sa.String(length=36), nullable=True),
        sa.Column("superseded_by_connection_id", sa.String(length=36), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by_user_id", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint(
            "lifecycle_status IN ('disconnected','connecting','connected','permission_required','token_expired','error','revoked')",
            name="ck_tt_connection_lifecycle",
        ),
    )
    op.create_index("ix_tt_connection_tenant_life", "tiktok_connections", ["tenant_id", "lifecycle_status"])
    op.create_index("ix_tt_connection_open_id", "tiktok_connections", ["open_id"])
    op.create_index("ix_tiktok_connections_tenant_id", "tiktok_connections", ["tenant_id"])
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "CREATE UNIQUE INDEX uq_tt_open_id_active ON tiktok_connections (open_id) "
            "WHERE lifecycle_status NOT IN ('revoked','disconnected')"
        )

    op.create_table(
        "tiktok_credentials",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("connection_id", sa.String(length=36), sa.ForeignKey("tiktok_connections.id"), nullable=False),
        sa.Column("ciphertext", sa.Text(), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("access_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("refresh_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_tt_credential_tenant", "tiktok_credentials", ["tenant_id"])
    op.create_index("ix_tiktok_credentials_connection_id", "tiktok_credentials", ["connection_id"])

    op.create_table(
        "tiktok_audit_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("connection_id", sa.String(length=36), nullable=True),
        sa.Column("actor_user_id", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("detail", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_tt_audit_tenant_created", "tiktok_audit_events", ["tenant_id", "created_at"])

    op.create_table(
        "tiktok_webhook_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("event_id", sa.String(length=128), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("connection_id", sa.String(length=36), nullable=True),
        sa.Column("event_name", sa.String(length=64), nullable=False),
        sa.Column("processed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("tiktok_request_id", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("event_id", name="uq_tt_webhook_event_id"),
    )
    op.create_index("ix_tt_webhook_tenant", "tiktok_webhook_events", ["tenant_id"])

    op.create_table(
        "tiktok_media",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("connection_id", sa.String(length=36), sa.ForeignKey("tiktok_connections.id"), nullable=False),
        sa.Column("item_id", sa.String(length=64), nullable=False),
        sa.Column("caption", sa.Text(), nullable=False, server_default=""),
        sa.Column("thumbnail_url", sa.String(length=1024), nullable=False, server_default=""),
        sa.Column("share_url", sa.String(length=1024), nullable=False, server_default=""),
        sa.Column("create_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("last_comment_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("comment_cursor", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("tenant_id", "item_id", name="uq_tt_media_tenant_item"),
    )
    op.create_index("ix_tt_media_connection", "tiktok_media", ["connection_id"])

    op.create_table(
        "tiktok_comments",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("connection_id", sa.String(length=36), sa.ForeignKey("tiktok_connections.id"), nullable=False),
        sa.Column("media_id", sa.String(length=36), sa.ForeignKey("tiktok_media.id"), nullable=False),
        sa.Column("comment_id", sa.String(length=64), nullable=False),
        sa.Column("parent_comment_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("video_item_id", sa.String(length=64), nullable=False),
        sa.Column("author_user_id", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("author_username", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("author_avatar_url", sa.String(length=1024), nullable=False, server_default=""),
        sa.Column("text", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="public"),
        sa.Column("create_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_reply", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("ai_processed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("tenant_id", "comment_id", name="uq_tt_comment_tenant_id"),
        sa.CheckConstraint("status IN ('public','hidden','deleted','unknown')", name="ck_tt_comment_status"),
    )
    op.create_index("ix_tt_comment_connection_created", "tiktok_comments", ["connection_id", "create_time"])
    op.create_index("ix_tt_comment_media", "tiktok_comments", ["media_id"])

    op.create_table(
        "tiktok_comment_replies",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("connection_id", sa.String(length=36), sa.ForeignKey("tiktok_connections.id"), nullable=False),
        sa.Column("comment_id", sa.String(length=64), nullable=False),
        sa.Column("reply_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("delivery_status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tiktok_request_id", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("tiktok_reply_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("last_error", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("model", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("credits_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("automation_on", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("tenant_id", "comment_id", name="uq_tt_reply_tenant_comment"),
        sa.CheckConstraint(
            "delivery_status IN ('pending','sending','sent','failed','skipped','retrying')",
            name="ck_tt_reply_delivery",
        ),
    )
    op.create_index("ix_tt_reply_status", "tiktok_comment_replies", ["delivery_status"])

    op.create_table(
        "tiktok_conversations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("connection_id", sa.String(length=36), sa.ForeignKey("tiktok_connections.id"), nullable=False),
        sa.Column("conversation_id", sa.String(length=128), nullable=False),
        sa.Column("customer_open_id", sa.String(length=128), nullable=False),
        sa.Column("customer_username", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("customer_avatar_url", sa.String(length=1024), nullable=False, server_default=""),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_message_preview", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("unread_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ai_status", sa.String(length=32), nullable=False, server_default="idle"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("connection_id", "conversation_id", name="uq_tt_conv_connection_cid"),
    )
    op.create_index("ix_tt_conv_tenant", "tiktok_conversations", ["tenant_id"])

    op.create_table(
        "tiktok_messages",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("connection_id", sa.String(length=36), sa.ForeignKey("tiktok_connections.id"), nullable=False),
        sa.Column(
            "conversation_row_id", sa.String(length=36), sa.ForeignKey("tiktok_conversations.id"), nullable=False
        ),
        sa.Column("provider_message_id", sa.String(length=128), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("text", sa.Text(), nullable=False, server_default=""),
        sa.Column("message_type", sa.String(length=32), nullable=False, server_default="text"),
        sa.Column("delivery_status", sa.String(length=16), nullable=False, server_default="received"),
        sa.Column("tiktok_request_id", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("tenant_id", "provider_message_id", name="uq_tt_msg_tenant_provider"),
    )
    op.create_index("ix_tt_msg_conversation", "tiktok_messages", ["conversation_row_id", "created_at"])


def downgrade() -> None:
    op.drop_table("tiktok_messages")
    op.drop_table("tiktok_conversations")
    op.drop_table("tiktok_comment_replies")
    op.drop_table("tiktok_comments")
    op.drop_table("tiktok_media")
    op.drop_table("tiktok_webhook_events")
    op.drop_table("tiktok_audit_events")
    op.drop_table("tiktok_credentials")
    op.drop_table("tiktok_connections")
    op.drop_table("tiktok_oauth_attempts")
