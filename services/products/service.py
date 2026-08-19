"""AI Products business logic — CRUD, validation, hard delete."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from services.products.active_context import clear_for_product as clear_context_for_product
from services.products.image_index import build_index_from_media, remove_product_from_index
from services.products.media import load_media_meta
from services.products.reply_to_map import clear_for_product as clear_reply_for_product
from services.products.repository import ProductsRepository
from services.products.schemas import MAX_IMAGES, ProductWriteBody, product_to_dict


class ProductsError(Exception):
    def __init__(self, *, code: str, message: str, http_status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


class ProductsService:
    def __init__(self, session: Session) -> None:
        self.repo = ProductsRepository(session)
        self.session = session

    def list_products(self, *, tenant_id: str, limit: int = 200, offset: int = 0) -> dict[str, Any]:
        rows = self.repo.list_products(tenant_id=tenant_id, limit=limit, offset=offset)
        total = self.repo.count_products(tenant_id=tenant_id)
        return {"products": [product_to_dict(row) for row in rows], "total": total}

    def get_product(self, *, tenant_id: str, product_id: str) -> dict[str, Any]:
        row = self.repo.get_product(tenant_id=tenant_id, product_id=product_id)
        if row is None:
            raise ProductsError(code="NOT_FOUND", message="product_not_found", http_status=404)
        return product_to_dict(row)

    def create_product(self, *, tenant_id: str, body: ProductWriteBody, require_description: bool = True) -> dict[str, Any]:
        if require_description and not (body.description or "").strip():
            raise ProductsError(
                code="DESCRIPTION_REQUIRED",
                message="Product description is required.",
                http_status=400,
            )
        self._validate_images(tenant_id=tenant_id, images=body.images)
        row = self.repo.create_product(tenant_id=tenant_id, fields=self._product_fields(body))
        self.repo.replace_images(
            tenant_id=tenant_id,
            product_id=row.id,
            images=[img.model_dump() for img in body.images],
        )
        self.repo.replace_links(
            tenant_id=tenant_id,
            product_id=row.id,
            links=[link.model_dump() for link in body.links],
        )
        self._sync_image_index(tenant_id=tenant_id, product_id=row.id, images=body.images)
        self._refresh_search_metadata(row)
        self.session.flush()
        self.session.expire(row, ["images", "links"])
        refreshed = self.repo.get_product(tenant_id=tenant_id, product_id=row.id)
        assert refreshed is not None
        return product_to_dict(refreshed)

    def update_product(self, *, tenant_id: str, product_id: str, body: ProductWriteBody) -> dict[str, Any]:
        row = self.repo.get_product(tenant_id=tenant_id, product_id=product_id)
        if row is None:
            raise ProductsError(code="NOT_FOUND", message="product_not_found", http_status=404)
        from services.search_metadata.product_apply import product_content_payload

        previous = product_content_payload(row)
        self._validate_images(tenant_id=tenant_id, images=body.images)
        remove_product_from_index(self.session, tenant_id=tenant_id, product_id=product_id)
        fields = self._product_fields(body, existing=row)
        self.repo.update_product(row, fields=fields)
        self.repo.replace_images(
            tenant_id=tenant_id,
            product_id=row.id,
            images=[img.model_dump() for img in body.images],
        )
        self.repo.replace_links(
            tenant_id=tenant_id,
            product_id=row.id,
            links=[link.model_dump() for link in body.links],
        )
        self._sync_image_index(tenant_id=tenant_id, product_id=row.id, images=body.images)
        self.session.flush()
        refreshed_meta = self.repo.get_product(tenant_id=tenant_id, product_id=row.id)
        assert refreshed_meta is not None
        self._refresh_search_metadata(refreshed_meta, previous=previous)
        self.session.flush()
        self.session.expire(row, ["images", "links"])
        refreshed = self.repo.get_product(tenant_id=tenant_id, product_id=row.id)
        assert refreshed is not None
        return product_to_dict(refreshed)

    def delete_product(self, *, tenant_id: str, product_id: str) -> list[str]:
        row = self.repo.get_product(tenant_id=tenant_id, product_id=product_id)
        if row is None:
            raise ProductsError(code="NOT_FOUND", message="product_not_found", http_status=404)
        media_ids = self.repo.delete_product(row)
        remove_product_from_index(self.session, tenant_id=tenant_id, product_id=product_id)
        clear_context_for_product(self.session, tenant_id=tenant_id, product_id=product_id)
        clear_reply_for_product(self.session, tenant_id=tenant_id, product_id=product_id)
        return media_ids

    def preview_csv(self, *, csv_text: str) -> dict[str, Any]:
        from services.products.import_service import ProductsImportError, preview_csv_rows

        try:
            return preview_csv_rows(csv_text)
        except ProductsImportError as exc:
            raise ProductsError(code=exc.code, message=exc.message, http_status=exc.http_status) from exc

    def import_csv(self, *, tenant_id: str, csv_text: str) -> dict[str, Any]:
        from services.products.import_service import import_csv_rows

        return import_csv_rows(self, tenant_id=tenant_id, csv_text=csv_text)

    def preview_xlsx(self, *, content: bytes) -> dict[str, Any]:
        from services.products.import_service import ProductsImportError, preview_xlsx_rows

        try:
            return preview_xlsx_rows(content)
        except ProductsImportError as exc:
            raise ProductsError(code=exc.code, message=exc.message, http_status=exc.http_status) from exc

    def import_xlsx(self, *, tenant_id: str, content: bytes) -> dict[str, Any]:
        from services.products.import_service import import_xlsx_rows

        return import_xlsx_rows(self, tenant_id=tenant_id, content=content)

    def _product_fields(self, body: ProductWriteBody, *, existing: Any | None = None) -> dict[str, Any]:
        from services.products.schemas import normalize_product_name

        description = (body.description or "").strip() or None
        if description is None and existing is not None:
            description = getattr(existing, "description", None)
        return {
            "name": body.name.strip(),
            "price": (body.price or "").strip() or None,
            "sizes": body.sizes,
            "colors": body.colors,
            "note": (body.note or "").strip() or None,
            "description": description,
            "description_normalized": normalize_product_name(description or "") or None,
            "availability": body.availability,
        }

    def _refresh_search_metadata(self, row: Any, *, previous: dict[str, Any] | None = None) -> None:
        from services.search_metadata.product_apply import enrich_product_row

        enrich_product_row(row, previous=previous)

    def _sync_image_index(self, *, tenant_id: str, product_id: str, images: list[Any]) -> None:
        refreshed = self.repo.get_product(tenant_id=tenant_id, product_id=product_id)
        if refreshed is None:
            return
        image_rows = sorted(refreshed.images or [], key=lambda i: i.sort_order)
        for img in images:
            media_id = str(getattr(img, "media_id", "") or "")
            if not media_id:
                continue
            product_image_id = next((row.id for row in image_rows if row.media_id == media_id), media_id)
            build_index_from_media(
                self.session,
                tenant_id=tenant_id,
                product_id=product_id,
                product_image_id=product_image_id,
                media_id=media_id,
            )

    def _validate_images(self, *, tenant_id: str, images: list[Any]) -> None:
        if len(images) > MAX_IMAGES:
            raise ProductsError(
                code="TOO_MANY_IMAGES",
                message=f"max_{MAX_IMAGES}_images",
                http_status=400,
            )
        for img in images:
            media_id = str(getattr(img, "media_id", "") or "")
            if not load_media_meta(tenant_id=tenant_id, media_id=media_id):
                raise ProductsError(
                    code="INVALID_MEDIA",
                    message="product_media_not_found",
                    http_status=400,
                )
