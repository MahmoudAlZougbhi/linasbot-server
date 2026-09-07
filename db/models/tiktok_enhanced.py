"""TikTok enhanced (Marketing API) identity / advertiser binding. No media URLs."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from db.models.base import Base

JsonType = JSON().with_variant(JSONB(), "postgresql")

ENHANCED_STATUSES = (
    "waiting_for_permission",
    "authorization_required",
    "identity_authorization_required",
    "reauthorization_required",
    "active",
    "limited",
    "error",
    "disconnected",
)


def _uuid() -> str:
    return str(uuid.uuid4())


class TikTokEnhancedBinding(Base):
    __tablename__ = "tiktok_enhanced_bindings"
    __table_args__ = (
        UniqueConstraint("connection_id", name="uq_tt_enhanced_connection"),
        Index("ix_tt_enhanced_tenant", "tenant_id"),
        CheckConstraint(
            "status IN ("
            "'waiting_for_permission','authorization_required','identity_authorization_required',"
            "'reauthorization_required','active','limited','error','disconnected'"
            ")",
            name="ck_tt_enhanced_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    connection_id: Mapped[str] = mapped_column(ForeignKey("tiktok_connections.id"), nullable=False)
    advertiser_credential_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    advertiser_id: Mapped[str] = mapped_column(String(64), nullable=False, server_default=text("''"))
    bc_id: Mapped[str] = mapped_column(String(64), nullable=False, server_default=text("''"))
    identity_id: Mapped[str] = mapped_column(String(128), nullable=False, server_default=text("''"))
    identity_type: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("''"))
    identity_authorized_bc_id: Mapped[str] = mapped_column(String(64), nullable=False, server_default=text("''"))
    status: Mapped[str] = mapped_column(String(64), nullable=False, server_default=text("'authorization_required'"))
    reason_code: Mapped[str] = mapped_column(String(64), nullable=False, server_default=text("''"))
    capabilities: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False, server_default=text("'{}'"))
    last_probe_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    probe_cooldown_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_probe_code: Mapped[str] = mapped_column(String(64), nullable=False, server_default=text("''"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
