"""Customer request drafts collected before a CustomerRequest is submitted."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from db.models.base import Base

JsonType = JSON().with_variant(JSONB(), "postgresql")

DRAFT_STATUSES = (
    "collecting",
    "paused",
    "ready",
    "submitted",
    "cancelled",
    "replaced",
    "definition_deleted",
    "expired",
)


def _uuid() -> str:
    return str(uuid.uuid4())


class CustomerRequestDraft(Base):
    __tablename__ = "customer_request_drafts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "draft_id", name="uq_reqdraft_tenant_draft"),
        Index("ix_reqdraft_tenant_customer_status", "tenant_id", "customer_id", "status"),
        Index("ix_reqdraft_tenant_definition", "tenant_id", "definition_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    draft_id: Mapped[str] = mapped_column(String(64), nullable=False)
    customer_id: Mapped[str] = mapped_column(String(128), nullable=False)
    conversation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    definition_id: Mapped[str] = mapped_column(String(64), nullable=False)
    definition_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    destination: Mapped[str] = mapped_column(String(32), nullable=False, default="general")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="collecting")
    values_json: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False, default=dict)
    missing_json: Mapped[list[Any]] = mapped_column(JsonType, nullable=False, default=list)
    items_json: Mapped[list[Any]] = mapped_column(JsonType, nullable=False, default=list)
    linked_entities_json: Mapped[list[Any]] = mapped_column(JsonType, nullable=False, default=list)
    last_idempotency: Mapped[str | None] = mapped_column(String(64), nullable=True)
    submitted_request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
