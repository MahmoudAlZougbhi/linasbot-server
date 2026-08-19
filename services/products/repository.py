"""Repository for AI Products (tenant-scoped Postgres)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from db.models.products import Product, ProductImage, ProductLink
from services.products.availability import CUSTOMER_SEARCH_AVAILABILITY, is_customer_searchable
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
            description=fields.get("description"),
            description_normalized=fields.get("description_normalized"),
            availability=fields.get("availability") or "in_stock",
            ai_search_title=fields.get("ai_search_title"),
            ai_search_description=fields.get("ai_search_description"),
            ai_search_keywords=fields.get("ai_search_keywords"),
            ai_search_title_normalized=fields.get("ai_search_title_normalized"),
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
        if "description" in fields:
            row.description = fields["description"]
            row.description_normalized = fields.get("description_normalized") or (
                normalize_product_name(fields["description"] or "") if fields["description"] else None
            )
        if "availability" in fields:
            row.availability = fields["availability"]
        if "ai_search_title" in fields:
            row.ai_search_title = fields["ai_search_title"]
        if "ai_search_description" in fields:
            row.ai_search_description = fields["ai_search_description"]
        if "ai_search_keywords" in fields:
            row.ai_search_keywords = fields["ai_search_keywords"]
        if "ai_search_title_normalized" in fields:
            row.ai_search_title_normalized = fields["ai_search_title_normalized"]
        row.updated_at = _now()
        self.session.flush()
        return row

    def replace_images(self, *, tenant_id: str, product_id: str, images: list[dict[str, Any]]) -> None:
        existing = (
            self.session.execute(
                select(ProductImage).where(
                    ProductImage.tenant_id == tenant_id,
                    ProductImage.product_id == product_id,
                )
            )
            .scalars()
            .all()
        )
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
        existing = (
            self.session.execute(
                select(ProductLink).where(
                    ProductLink.tenant_id == tenant_id,
                    ProductLink.product_id == product_id,
                )
            )
            .scalars()
            .all()
        )
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
        customer_facing: bool = True,
    ) -> list[Product]:
        normalized = normalize_product_name(query)
        if not normalized:
            return []
        filters = [Product.tenant_id == tenant_id]
        like_clauses = [Product.name_normalized.contains(normalized)]
        if hasattr(Product, "description_normalized"):
            like_clauses.append(Product.description_normalized.contains(normalized))
        if hasattr(Product, "ai_search_title_normalized"):
            like_clauses.append(Product.ai_search_title_normalized.contains(normalized))
        filters.append(or_(*like_clauses))
        if customer_facing:
            filters.append(Product.availability.in_(list(CUSTOMER_SEARCH_AVAILABILITY)))
        stmt = (
            select(Product)
            .where(*filters)
            .options(selectinload(Product.images), selectinload(Product.links))
            .order_by(Product.updated_at.desc())
            .limit(limit)
        )
        return list(self.session.execute(stmt).scalars().all())

    def list_all_for_tenant(self, *, tenant_id: str, customer_facing: bool = True) -> list[Product]:
        filters = [Product.tenant_id == tenant_id]
        if customer_facing:
            filters.append(Product.availability.in_(list(CUSTOMER_SEARCH_AVAILABILITY)))
        stmt = select(Product).where(*filters).options(selectinload(Product.images), selectinload(Product.links))
        return list(self.session.execute(stmt).scalars().all())

    def find_by_link_url(self, *, tenant_id: str, normalized_url: str) -> Product | None:
        from urllib.parse import urlparse

        needle = str(normalized_url or "").strip().lower()
        if not needle:
            return None
        stmt = (
            select(Product)
            .join(ProductLink, ProductLink.product_id == Product.id)
            .where(Product.tenant_id == tenant_id, ProductLink.tenant_id == tenant_id)
            .options(selectinload(Product.images), selectinload(Product.links))
        )
        for row in self.session.execute(stmt).scalars().all():
            if not is_customer_searchable(row.availability):
                continue
            for link in row.links or []:
                raw = str(link.url or "").strip()
                if not raw:
                    continue
                parsed = urlparse(raw if "://" in raw else f"https://{raw}")
                host = (parsed.netloc or "").removeprefix("www.")
                path = (parsed.path or "").rstrip("/")
                candidate = f"{host}{path}".lower()
                if candidate == needle or needle in candidate or candidate in needle:
                    return row
        return None
