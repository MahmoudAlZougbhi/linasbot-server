"""Repository for AI Products (tenant-scoped Postgres)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from db.models.products import Product, ProductImage, ProductLink
from services.products.schemas import normalize_product_name


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


class ProductsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_products(self, *, tenant_id: str, limit: int = 200, offset: int = 0) -> list[Product]:
        stmt = (
            select(Product)
            .where(Product.tenant_id == tenant_id)
            .options(selectinload(Product.images), selectinload(Product.links))
            .order_by(Product.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self.session.execute(stmt).scalars().all())

    def count_products(self, *, tenant_id: str) -> int:
        from sqlalchemy import func

        stmt = select(func.count()).select_from(Product).where(Product.tenant_id == tenant_id)
        return int(self.session.execute(stmt).scalar_one())

    def get_product(self, *, tenant_id: str, product_id: str) -> Product | None:
        stmt = (
            select(Product)
            .where(Product.tenant_id == tenant_id, Product.id == product_id)
            .options(selectinload(Product.images), selectinload(Product.links))
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def create_product(self, *, tenant_id: str, fields: dict[str, Any]) -> Product:
        row = Product(
            id=_uuid(),
            tenant_id=tenant_id,
            name=fields["name"],
            name_normalized=normalize_product_name(fields["name"]),
            price=fields.get("price"),
            sizes=fields.get("sizes"),
            colors=fields.get("colors"),
            note=fields.get("note"),
            created_at=_now(),
            updated_at=_now(),
        )
        self.session.add(row)
        self.session.flush()
        return row

    def update_product(self, row: Product, *, fields: dict[str, Any]) -> Product:
        if "name" in fields:
            row.name = fields["name"]
            row.name_normalized = normalize_product_name(fields["name"])
        if "price" in fields:
            row.price = fields["price"]
        if "sizes" in fields:
            row.sizes = fields["sizes"]
        if "colors" in fields:
            row.colors = fields["colors"]
        if "note" in fields:
            row.note = fields["note"]
        row.updated_at = _now()
        self.session.flush()
        return row

    def replace_images(self, *, tenant_id: str, product_id: str, images: list[dict[str, Any]]) -> None:
        existing = self.session.execute(
            select(ProductImage).where(
                ProductImage.tenant_id == tenant_id,
                ProductImage.product_id == product_id,
            )
        ).scalars().all()
        for row in existing:
            self.session.delete(row)
        self.session.flush()
        for img in images:
            self.session.add(
                ProductImage(
                    id=_uuid(),
                    tenant_id=tenant_id,
                    product_id=product_id,
                    media_id=img["media_id"],
                    sort_order=int(img["sort_order"]),
                    created_at=_now(),
                )
            )
        self.session.flush()

    def replace_links(self, *, tenant_id: str, product_id: str, links: list[dict[str, Any]]) -> None:
        existing = self.session.execute(
            select(ProductLink).where(
                ProductLink.tenant_id == tenant_id,
                ProductLink.product_id == product_id,
            )
        ).scalars().all()
        for row in existing:
            self.session.delete(row)
        self.session.flush()
        for link in links:
            self.session.add(
                ProductLink(
                    id=_uuid(),
                    tenant_id=tenant_id,
                    product_id=product_id,
                    url=link["url"],
                    label=link.get("label"),
                    sort_order=int(link.get("sort_order") or 0),
                    created_at=_now(),
                )
            )
        self.session.flush()

    def delete_product(self, row: Product) -> list[str]:
        media_ids = [img.media_id for img in row.images]
        self.session.delete(row)
        self.session.flush()
        return media_ids

    def search_by_title_prefix(
        self,
        *,
        tenant_id: str,
        query: str,
        limit: int = 10,
    ) -> list[Product]:
        normalized = normalize_product_name(query)
        if not normalized:
            return []
        stmt = (
            select(Product)
            .where(
                Product.tenant_id == tenant_id,
                Product.name_normalized.contains(normalized),
            )
            .options(selectinload(Product.images), selectinload(Product.links))
            .order_by(Product.updated_at.desc())
            .limit(limit)
        )
        return list(self.session.execute(stmt).scalars().all())

    def list_all_for_tenant(self, *, tenant_id: str) -> list[Product]:
        stmt = (
            select(Product)
            .where(Product.tenant_id == tenant_id)
            .options(selectinload(Product.images), selectinload(Product.links))
        )
        return list(self.session.execute(stmt).scalars().all())
