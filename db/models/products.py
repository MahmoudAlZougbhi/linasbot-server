"""AI Products ORM — tenant-scoped catalog (PostgreSQL SoT)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from db.models.base import Base

JsonType = JSON().with_variant(JSONB(), "postgresql")


def _uuid() -> str:
    return str(uuid.uuid4())


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        Index("ix_products_tenant_updated", "tenant_id", "updated_at"),
        Index("ix_products_tenant_name_normalized", "tenant_id", "name_normalized"),
        Index("ix_products_tenant_availability", "tenant_id", "availability"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    name_normalized: Mapped[str] = mapped_column(String(512), nullable=False)
    price: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sizes: Mapped[list[Any] | None] = mapped_column(JsonType, nullable=True)
    colors: Mapped[list[Any] | None] = mapped_column(JsonType, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    availability: Mapped[str] = mapped_column(String(32), nullable=False, server_default="in_stock")
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

    images: Mapped[list[ProductImage]] = relationship(
        "ProductImage",
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="ProductImage.sort_order",
    )
    links: Mapped[list[ProductLink]] = relationship(
        "ProductLink",
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="ProductLink.sort_order",
    )


class ProductImage(Base):
    __tablename__ = "product_images"
    __table_args__ = (
        CheckConstraint("sort_order >= 0 AND sort_order < 3", name="ck_product_images_sort_order"),
        Index("ix_product_images_tenant_media", "tenant_id", "media_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    product_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    media_id: Mapped[str] = mapped_column(String(64), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    product: Mapped[Product] = relationship("Product", back_populates="images")


class ProductLink(Base):
    __tablename__ = "product_links"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    product_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str | None] = mapped_column(String(256), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    product: Mapped[Product] = relationship("Product", back_populates="links")


class ProductConversationContext(Base):
    __tablename__ = "product_conversation_context"
    __table_args__ = (
        Index("ix_product_ctx_tenant_conversation", "tenant_id", "conversation_id", unique=True),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    conversation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    active_product_id: Mapped[str] = mapped_column(String(36), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class ProductImageFingerprint(Base):
  __tablename__ = "product_image_fingerprints"
  __table_args__ = (
      Index("ix_product_img_fp_tenant_sha256", "tenant_id", "sha256"),
      Index("ix_product_img_fp_tenant_product", "tenant_id", "product_id"),
      Index("ix_product_img_fp_tenant_media", "tenant_id", "media_id", unique=True),
  )

  id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
  tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
  product_id: Mapped[str] = mapped_column(
      String(36),
      ForeignKey("products.id", ondelete="CASCADE"),
      nullable=False,
      index=True,
  )
  product_image_id: Mapped[str] = mapped_column(String(36), nullable=False)
  media_id: Mapped[str] = mapped_column(String(64), nullable=False)
  sha256: Mapped[str] = mapped_column(String(64), nullable=False)
  phash: Mapped[str] = mapped_column(String(16), nullable=False)
  histogram: Mapped[list[Any] | None] = mapped_column(JsonType, nullable=True)
  created_at: Mapped[datetime] = mapped_column(
      DateTime(timezone=True),
      nullable=False,
      server_default=func.now(),
  )


class ProductSentMessage(Base):
    __tablename__ = "product_sent_messages"
    __table_args__ = (
        Index("ix_product_sent_msg_lookup", "tenant_id", "channel", "sent_message_id", unique=True),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    conversation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    channel: Mapped[str] = mapped_column(String(64), nullable=False)
    sent_message_id: Mapped[str] = mapped_column(String(128), nullable=False)
    product_id: Mapped[str] = mapped_column(String(36), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
