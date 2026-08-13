"""Meta app registry ORM models (PostgreSQL SoT for bindings / credentials).

Additive tables for META_REGISTRY_BACKEND=postgres|dual. Ciphertext is stored
as-is (no re-seal). Partial unique indexes for active exclusivity live in Alembic.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from db.models.base import Base

JsonType = JSON().with_variant(JSONB(), "postgresql")


def _uuid() -> str:
    return str(uuid.uuid4())


class MetaAssetBindingRow(Base):
    __tablename__ = "meta_asset_bindings"
    __table_args__ = (
        Index("ix_meta_asset_bindings_tenant_channel", "tenant_id", "channel"),
        Index("ix_meta_asset_bindings_status", "status"),
        Index("ix_meta_asset_bindings_asset_id", "asset_id"),
    )

    binding_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    asset_id: Mapped[str] = mapped_column(String(128), nullable=False)
    page_id: Mapped[str] = mapped_column(String(128), nullable=False, server_default=text("''"))
    instagram_account_id: Mapped[str] = mapped_column(String(128), nullable=False, server_default=text("''"))
    app_key: Mapped[str] = mapped_column(String(64), nullable=False)
    credential_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    generation: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    created_at: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0"))
    updated_at: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0"))
    previous_binding_id: Mapped[str] = mapped_column(String(64), nullable=False, server_default=text("''"))
    page_name: Mapped[str] = mapped_column(String(255), nullable=False, server_default=text("''"))
    instagram_username: Mapped[str] = mapped_column(String(255), nullable=False, server_default=text("''"))
    authorized_meta_user_id_hash: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("''")
    )
    superseded_by_binding_id: Mapped[str] = mapped_column(String(64), nullable=False, server_default=text("''"))
    auth_flow: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'facebook_login'")
    )
    webhook_subscription_status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'unknown'")
    )
    webhook_subscribed_fields: Mapped[list[Any]] = mapped_column(
        JsonType, nullable=False, server_default=text("'[]'")
    )
    webhook_subscription_error: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    webhook_subscription_checked_at: Mapped[float] = mapped_column(
        Float, nullable=False, server_default=text("0")
    )


class MetaBindingCredentialRow(Base):
    __tablename__ = "meta_binding_credentials"
    __table_args__ = (Index("ix_meta_binding_credentials_binding_id", "binding_id"),)

    credential_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    binding_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("meta_asset_bindings.binding_id"),
        nullable=False,
    )
    sealed: Mapped[str] = mapped_column(Text, nullable=False)
    aad: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0"))
    archived_at: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0"))


class MetaOAuthStateRow(Base):
    __tablename__ = "meta_oauth_states"
    __table_args__ = (Index("ix_meta_oauth_states_expires_at", "expires_at"),)

    nonce: Mapped[str] = mapped_column(String(128), primary_key=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False, server_default=text("'{}'"))
    expires_at: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0"))


class MetaRegistryAuditEvent(Base):
    __tablename__ = "meta_registry_audit_events"
    __table_args__ = (
        Index("ix_meta_registry_audit_tenant_ts", "tenant_id", "timestamp"),
        Index("ix_meta_registry_audit_event", "event"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    timestamp: Mapped[float] = mapped_column(Float, nullable=False)
    event: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_id_hash: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("''"))
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, server_default=text("''"))
    channel: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("''"))
    asset_id_hash: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("''"))
    app_key: Mapped[str] = mapped_column(String(64), nullable=False, server_default=text("''"))
    binding_id: Mapped[str] = mapped_column(String(64), nullable=False, server_default=text("''"))
    result: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'ok'"))
