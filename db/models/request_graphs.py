"""Request definition graphs compiled from owner natural-language rules."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from db.models.base import Base

JsonType = JSON().with_variant(JSONB(), "postgresql")


def _uuid() -> str:
    return str(uuid.uuid4())


class RequestDefinitionGraph(Base):
    __tablename__ = "request_definition_graphs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "source_item_id", "revision", name="uq_reqdef_tenant_source_rev"),
        Index("ix_reqdef_tenant_definition", "tenant_id", "definition_id"),
        Index("ix_reqdef_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    definition_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source_item_id: Mapped[str] = mapped_column(String(128), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    source_text_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    destination: Mapped[str] = mapped_column(String(32), nullable=False, default="general")
    graph_json: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False, default=dict)
    confirmation_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    needs_owner_clarification: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    links: Mapped[list[RequestDefinitionLink]] = relationship(
        "RequestDefinitionLink",
        back_populates="graph",
        cascade="all, delete-orphan",
    )


class RequestDefinitionLink(Base):
    __tablename__ = "request_definition_links"
    __table_args__ = (Index("ix_reqdef_link_tenant_def", "tenant_id", "definition_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    graph_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("request_definition_graphs.id", ondelete="CASCADE"), nullable=False
    )
    definition_id: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)

    graph: Mapped[RequestDefinitionGraph] = relationship("RequestDefinitionGraph", back_populates="links")
