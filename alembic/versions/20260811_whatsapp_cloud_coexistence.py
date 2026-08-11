"""WhatsApp Cloud coexistence domain tables.

Revision ID: 20260811_whatsapp_cloud
Revises:
Create Date: 2026-08-11
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260811_whatsapp_cloud"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "whatsapp_connection_attempts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("state_hash", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("actor_user_id", sa.String(length=128), nullable=False),
        sa.Column("meta_app_key", sa.String(length=64), nullable=False, server_default="linas_first_party"),
        sa.Column("return_surface", sa.String(length=16), nullable=False),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column(
            "feature_type",
            sa.String(length=64),
            nullable=False,
            server_default="whatsapp_business_app_onboarding",
        ),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome_code", sa.String(length=64), nullable=True),
        sa.Column("outcome_detail", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("state_hash", name="uq_wa_attempt_state_hash"),
        sa.CheckConstraint(
            "status IN ('pending','consumed','expired','cancelled','failed','completed')",
            name="ck_wa_attempt_status",
        ),
        sa.CheckConstraint(
            "return_surface IN ('mobile','web','bridge')",
            name="ck_wa_attempt_return_surface",
        ),
    )
    op.create_index("ix_wa_attempt_tenant_status", "whatsapp_connection_attempts", ["tenant_id", "status"])
    op.create_index(
        "ix_whatsapp_connection_attempts_tenant_id",
        "whatsapp_connection_attempts",
        ["tenant_id"],
    )
    op.create_index(
        "ix_whatsapp_connection_attempts_correlation_id",
        "whatsapp_connection_attempts",
        ["correlation_id"],
    )

    op.create_table(
        "whatsapp_connections",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=128), nullable=False),
        sa.Column("meta_app_key", sa.String(length=64), nullable=False, server_default="linas_first_party"),
        sa.Column("meta_app_id", sa.String(length=32), nullable=False),
        sa.Column("waba_id", sa.String(length=64), nullable=False),
        sa.Column("phone_number_id", sa.String(length=64), nullable=False),
        sa.Column("display_phone_number", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("display_phone_last4", sa.String(length=4), nullable=False, server_default=""),
        sa.Column("verified_name", sa.String(length=255), nullable=False, server_default=""),
        sa.Column(
            "coexistence_mode",
            sa.String(length=64),
            nullable=False,
            server_default="whatsapp_business_app_onboarding",
        ),
        sa.Column("lifecycle_status", sa.String(length=32), nullable=False, server_default="provisioning"),
        sa.Column("credential_id", sa.String(length=36), nullable=True),
        sa.Column("credential_generation", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("granted_scopes", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("webhook_subscription_status", sa.String(length=32), nullable=False, server_default="unknown"),
        sa.Column("webhook_subscribed_fields", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("webhook_last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("health_status", sa.String(length=32), nullable=False, server_default="unknown"),
        sa.Column("health_detail", sa.String(length=255), nullable=True),
        sa.Column("ai_default_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("history_sync_status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("previous_connection_id", sa.String(length=36), nullable=True),
        sa.Column("superseded_by_connection_id", sa.String(length=36), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_reason", sa.String(length=255), nullable=True),
        sa.Column("revoked_by_user_id", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint(
            "lifecycle_status IN ("
            "'disconnected','starting','awaiting_meta','provisioning','syncing_history',"
            "'connected','needs_attention','failed','revoked'"
            ")",
            name="ck_wa_connection_lifecycle",
        ),
        sa.CheckConstraint(
            "coexistence_mode IN ('whatsapp_business_app_onboarding','api_setup_forbidden')",
            name="ck_wa_connection_coexistence",
        ),
    )
    op.create_index("ix_wa_connection_tenant_lifecycle", "whatsapp_connections", ["tenant_id", "lifecycle_status"])
    op.create_index("ix_wa_connection_waba", "whatsapp_connections", ["waba_id"])
    op.create_index("ix_whatsapp_connections_tenant_id", "whatsapp_connections", ["tenant_id"])
    # One active phone_number_id globally (Postgres partial unique).
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            sa.text(
                "CREATE UNIQUE INDEX uq_wa_active_phone_number_id "
                "ON whatsapp_connections (phone_number_id) "
                "WHERE lifecycle_status IN ("
                "'connected','provisioning','syncing_history','needs_attention','awaiting_meta','starting'"
                ")"
            )
        )

    op.create_table(
        "whatsapp_credentials",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("connection_id", sa.String(length=36), sa.ForeignKey("whatsapp_connections.id"), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("ciphertext", sa.Text(), nullable=False),
        sa.Column("encryption_key_version", sa.String(length=32), nullable=False, server_default="v1"),
        sa.Column("token_type", sa.String(length=32), nullable=False, server_default="user"),
        sa.Column("scopes", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint(
            "token_type IN ('user','system_user','business')",
            name="ck_wa_credential_token_type",
        ),
    )
    op.create_index("ix_wa_credential_tenant", "whatsapp_credentials", ["tenant_id"])
    op.create_index("ix_whatsapp_credentials_connection_id", "whatsapp_credentials", ["connection_id"])

    op.create_table(
        "whatsapp_conversations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("connection_id", sa.String(length=36), sa.ForeignKey("whatsapp_connections.id"), nullable=False),
        sa.Column("customer_wa_id", sa.String(length=64), nullable=False),
        sa.Column("customer_profile_name", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("control_state", sa.String(length=32), nullable=False, server_default="AI_ACTIVE"),
        sa.Column("control_epoch", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("pause_reason", sa.String(length=64), nullable=True),
        sa.Column("last_inbound_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_human_outbound_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_ai_outbound_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("service_window_opens_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("connection_id", "customer_wa_id", name="uq_wa_conversation_connection_customer"),
        sa.CheckConstraint(
            "control_state IN ('AI_ACTIVE','HUMAN_PAUSED')",
            name="ck_wa_conversation_control_state",
        ),
    )
    op.create_index("ix_wa_conversation_tenant", "whatsapp_conversations", ["tenant_id"])
    op.create_index("ix_whatsapp_conversations_connection_id", "whatsapp_conversations", ["connection_id"])

    op.create_table(
        "whatsapp_messages",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("connection_id", sa.String(length=36), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), sa.ForeignKey("whatsapp_conversations.id"), nullable=False),
        sa.Column("provider_message_id", sa.String(length=128), nullable=False),
        sa.Column("origin", sa.String(length=32), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("message_type", sa.String(length=32), nullable=False, server_default="text"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="received"),
        sa.Column("content_redacted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("content_preview", sa.String(length=120), nullable=True),
        sa.Column("media_mime", sa.String(length=128), nullable=True),
        sa.Column("media_id", sa.String(length=128), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("provider_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("provider_message_id", name="uq_wa_message_provider_id"),
        sa.CheckConstraint(
            "origin IN ('CUSTOMER','CLOUD_API','BUSINESS_APP','HISTORY','SYSTEM')",
            name="ck_wa_message_origin",
        ),
        sa.CheckConstraint(
            "direction IN ('inbound','outbound')",
            name="ck_wa_message_direction",
        ),
    )
    op.create_index("ix_wa_message_conversation", "whatsapp_messages", ["conversation_id"])
    op.create_index("ix_wa_message_tenant_created", "whatsapp_messages", ["tenant_id", "created_at"])
    op.create_index("ix_whatsapp_messages_connection_id", "whatsapp_messages", ["connection_id"])

    op.create_table(
        "whatsapp_outbound_intents",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("connection_id", sa.String(length=36), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("triggering_inbound_message_id", sa.String(length=36), nullable=True),
        sa.Column("control_epoch_at_create", sa.Integer(), nullable=False),
        sa.Column("control_epoch_at_send", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="AI"),
        sa.Column("dispatch_state", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("provider_wamid", sa.String(length=128), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_detail", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("idempotency_key", name="uq_wa_outbound_idempotency"),
        sa.CheckConstraint(
            "dispatch_state IN ("
            "'pending','sending','sent','failed','suppressed','reconciliation_required'"
            ")",
            name="ck_wa_outbound_dispatch_state",
        ),
    )
    op.create_index("ix_wa_outbound_conversation", "whatsapp_outbound_intents", ["conversation_id"])
    op.create_index("ix_whatsapp_outbound_intents_tenant_id", "whatsapp_outbound_intents", ["tenant_id"])

    op.create_table(
        "whatsapp_webhook_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=True),
        sa.Column("connection_id", sa.String(length=36), nullable=True),
        sa.Column("event_key", sa.String(length=128), nullable=False),
        sa.Column("event_kind", sa.String(length=64), nullable=False),
        sa.Column("processing_state", sa.String(length=32), nullable=False, server_default="claimed"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("error_detail", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("event_key", name="uq_wa_webhook_event_key"),
        sa.CheckConstraint(
            "processing_state IN ('claimed','processed','failed','dead_letter','ignored')",
            name="ck_wa_webhook_processing_state",
        ),
    )
    op.create_index("ix_wa_webhook_tenant_created", "whatsapp_webhook_events", ["tenant_id", "created_at"])

    op.create_table(
        "whatsapp_audit_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("connection_id", sa.String(length=36), nullable=True),
        sa.Column("conversation_id", sa.String(length=36), nullable=True),
        sa.Column("actor_user_id", sa.String(length=128), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_wa_audit_tenant_created", "whatsapp_audit_events", ["tenant_id", "created_at"])

    op.create_table(
        "whatsapp_pilot_entitlements",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("granted_by_user_id", sa.String(length=128), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by_user_id", sa.String(length=128), nullable=True),
        sa.UniqueConstraint("tenant_id", name="uq_wa_pilot_tenant"),
        sa.CheckConstraint("status IN ('active','revoked')", name="ck_wa_pilot_status"),
    )


def downgrade() -> None:
    op.drop_table("whatsapp_pilot_entitlements")
    op.drop_table("whatsapp_audit_events")
    op.drop_table("whatsapp_webhook_events")
    op.drop_table("whatsapp_outbound_intents")
    op.drop_table("whatsapp_messages")
    op.drop_table("whatsapp_conversations")
    op.drop_table("whatsapp_credentials")
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(sa.text("DROP INDEX IF EXISTS uq_wa_active_phone_number_id"))
    op.drop_table("whatsapp_connections")
    op.drop_table("whatsapp_connection_attempts")
