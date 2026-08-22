"""Tenant runtime configuration ORM (Postgres HA SoT).

Authoritative for channel toggles (CM actions), per-asset comment settings,
CM draft metadata, and published pointer/actions metadata. Node-local files are
optional caches only.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import BigInteger, Boolean, Float, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from db.models.base import Base

JsonType = JSON().with_variant(JSONB(), "postgresql")


class TenantCmDraftSectionRow(Base):
    __tablename__ = "tenant_cm_draft_sections"
    __table_args__ = (Index("ix_tenant_cm_draft_sections_tenant", "tenant_id"),)

    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    section: Mapped[str] = mapped_column(String(64), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    etag: Mapped[str] = mapped_column(String(128), nullable=False, server_default=text("''"))
    payload: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False, server_default=text("'{}'"))
    updated_by: Mapped[str] = mapped_column(String(128), nullable=False, server_default=text("''"))
    updated_at: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0"))


class TenantCmPublishedStateRow(Base):
    __tablename__ = "tenant_cm_published_state"

    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    content_version_id: Mapped[str] = mapped_column(String(64), nullable=False, server_default=text("''"))
    index_version_id: Mapped[str] = mapped_column(String(64), nullable=False, server_default=text("''"))
    checksums: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False, server_default=text("'{}'"))
    actions_payload: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False, server_default=text("'{}'"))
    embedding_provider: Mapped[str] = mapped_column(String(64), nullable=False, server_default=text("''"))
    embedding_model: Mapped[str] = mapped_column(String(128), nullable=False, server_default=text("''"))
    embedding_dimensions: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    embedding_version: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("''"))
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    revision: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    published_at: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0"))
    updated_at: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0"))


class TenantMetaCommentAssetSettingRow(Base):
    __tablename__ = "tenant_meta_comment_asset_settings"
    __table_args__ = (Index("ix_tenant_meta_comment_asset_tenant", "tenant_id"),)

    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    asset_key: Mapped[str] = mapped_column(String(256), primary_key=True)
    app_key: Mapped[str] = mapped_column(String(64), nullable=False, server_default=text("''"))
    channel: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("''"))
    asset_id: Mapped[str] = mapped_column(String(128), nullable=False, server_default=text("''"))
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    instructions: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    revision: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    updated_at: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0"))


class MetaCommentSyncCursorRow(Base):
    __tablename__ = "meta_comment_sync_cursors"

    binding_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    cursor_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    cursor_value: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    revision: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    updated_at: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0"))


class TenantRuntimeConfigMigrationRow(Base):
    __tablename__ = "tenant_runtime_config_migrations"

    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    migration_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    applied_at: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0"))
    audit: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False, server_default=text("'{}'"))
