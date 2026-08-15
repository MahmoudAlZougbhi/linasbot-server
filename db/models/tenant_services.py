"""Tenant-scoped services with priced options (PostgreSQL SoT)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.models.base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class TenantService(Base):
    __tablename__ = "services"
    __table_args__ = (
        Index("ix_services_tenant_updated", "tenant_id", "updated_at"),
        Index("ix_services_tenant_name_normalized", "tenant_id", "name_normalized"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    name_normalized: Mapped[str] = mapped_column(String(512), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    options: Mapped[list[ServiceOption]] = relationship(
        "ServiceOption",
        back_populates="service",
        cascade="all, delete-orphan",
        order_by="ServiceOption.sort_order",
    )


class ServiceOption(Base):
    __tablename__ = "service_options"
    __table_args__ = (
        Index("ix_service_options_service_sort", "service_id", "sort_order"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    service_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("services.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    machine_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    body_part: Mapped[str | None] = mapped_column(String(256), nullable=True)
    staff_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    price: Mapped[str] = mapped_column(String(128), nullable=False)
    currency: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'USD'"))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    service: Mapped[TenantService] = relationship("TenantService", back_populates="options")
