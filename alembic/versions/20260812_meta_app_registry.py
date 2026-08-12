"""Meta app registry tables (additive Postgres SoT).

Revision ID: 20260812_meta_app_registry
Revises: 20260811_wa_app_review_source
Create Date: 2026-08-12

Upgrade:
  - Creates meta_asset_bindings, meta_binding_credentials, meta_oauth_states,
    meta_registry_audit_events.
  - Postgres-only partial unique indexes for active Facebook / Instagram exclusivity.
  - Additive only; does not rewrite file-backed registry data.
  - Safe to apply without Customer Requests migration (Requests revises this revision).

Do NOT enable META_REGISTRY_BACKEND=postgres/dual on production without import+cutover approval.

Rollback:
  - downgrade() drops the new tables / indexes in FK-safe order.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260812_meta_app_registry"
down_revision: str | None = "20260811_wa_app_review_source"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JsonType = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "meta_asset_bindings",
        sa.Column("binding_id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("asset_id", sa.String(length=128), nullable=False),
        sa.Column("page_id", sa.String(length=128), nullable=False, server_default=sa.text("''")),
        sa.Column(
            "instagram_account_id",
            sa.String(length=128),
            nullable=False,
            server_default=sa.text("''"),
        ),
        sa.Column("app_key", sa.String(length=64), nullable=False),
        sa.Column("credential_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("updated_at", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "previous_binding_id",
            sa.String(length=64),
            nullable=False,
            server_default=sa.text("''"),
        ),
        sa.Column("page_name", sa.String(length=255), nullable=False, server_default=sa.text("''")),
        sa.Column(
            "instagram_username",
            sa.String(length=255),
            nullable=False,
            server_default=sa.text("''"),
        ),
        sa.Column(
            "authorized_meta_user_id_hash",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("''"),
        ),
        sa.Column(
            "superseded_by_binding_id",
            sa.String(length=64),
            nullable=False,
            server_default=sa.text("''"),
        ),
        sa.Column(
            "auth_flow",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'facebook_login'"),
        ),
        sa.Column(
            "webhook_subscription_status",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'unknown'"),
        ),
        sa.Column("webhook_subscribed_fields", JsonType, nullable=False, server_default=sa.text("'[]'")),
        sa.Column(
            "webhook_subscription_error",
            sa.Text(),
            nullable=False,
            server_default=sa.text("''"),
        ),
        sa.Column(
            "webhook_subscription_checked_at",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.create_index(
        "ix_meta_asset_bindings_tenant_channel",
        "meta_asset_bindings",
        ["tenant_id", "channel"],
    )
    op.create_index("ix_meta_asset_bindings_status", "meta_asset_bindings", ["status"])
    op.create_index("ix_meta_asset_bindings_asset_id", "meta_asset_bindings", ["asset_id"])

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            sa.text(
                "CREATE UNIQUE INDEX uq_meta_active_facebook_asset "
                "ON meta_asset_bindings (channel, asset_id) "
                "WHERE status = 'active' AND channel = 'facebook'"
            )
        )
        op.execute(
            sa.text(
                "CREATE UNIQUE INDEX uq_meta_active_instagram_asset "
                "ON meta_asset_bindings (channel, auth_flow, asset_id) "
                "WHERE status = 'active' AND channel = 'instagram'"
            )
        )

    op.create_table(
        "meta_binding_credentials",
        sa.Column("credential_id", sa.String(length=64), primary_key=True),
        sa.Column(
            "binding_id",
            sa.String(length=64),
            sa.ForeignKey("meta_asset_bindings.binding_id"),
            nullable=False,
        ),
        sa.Column("sealed", sa.Text(), nullable=False),
        sa.Column("aad", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False, server_default=sa.text("0")),
    )
    op.create_index(
        "ix_meta_binding_credentials_binding_id",
        "meta_binding_credentials",
        ["binding_id"],
    )

    op.create_table(
        "meta_oauth_states",
        sa.Column("nonce", sa.String(length=128), primary_key=True),
        sa.Column("payload", JsonType, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("expires_at", sa.Float(), nullable=False, server_default=sa.text("0")),
    )
    op.create_index("ix_meta_oauth_states_expires_at", "meta_oauth_states", ["expires_at"])

    op.create_table(
        "meta_registry_audit_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("timestamp", sa.Float(), nullable=False),
        sa.Column("event", sa.String(length=64), nullable=False),
        sa.Column("actor_id_hash", sa.String(length=32), nullable=False, server_default=sa.text("''")),
        sa.Column("tenant_id", sa.String(length=64), nullable=False, server_default=sa.text("''")),
        sa.Column("channel", sa.String(length=32), nullable=False, server_default=sa.text("''")),
        sa.Column("asset_id_hash", sa.String(length=32), nullable=False, server_default=sa.text("''")),
        sa.Column("app_key", sa.String(length=64), nullable=False, server_default=sa.text("''")),
        sa.Column("binding_id", sa.String(length=64), nullable=False, server_default=sa.text("''")),
        sa.Column("result", sa.String(length=32), nullable=False, server_default=sa.text("'ok'")),
    )
    op.create_index(
        "ix_meta_registry_audit_tenant_ts",
        "meta_registry_audit_events",
        ["tenant_id", "timestamp"],
    )
    op.create_index("ix_meta_registry_audit_event", "meta_registry_audit_events", ["event"])


def downgrade() -> None:
    op.drop_table("meta_registry_audit_events")
    op.drop_table("meta_oauth_states")
    op.drop_table("meta_binding_credentials")
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(sa.text("DROP INDEX IF EXISTS uq_meta_active_instagram_asset"))
        op.execute(sa.text("DROP INDEX IF EXISTS uq_meta_active_facebook_asset"))
    op.drop_table("meta_asset_bindings")
