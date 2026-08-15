"""AI Products business logic — CRUD, validation, hard delete."""

from __future__ import annotations

import csv
import io
from typing import Any

from sqlalchemy.orm import Session

from services.products.image_index import remove_product_from_index, upsert_product_image_index
from services.products.media import load_media_meta
from services.products.repository import ProductsRepository
from services.products.schemas import MAX_IMAGES, ProductWriteBody, normalize_product_name, product_to_dict


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
        return {
            "products": [product_to_dict(row) for row in rows],
            "total": total,
        }

    def get_product(self, *, tenant_id: str, product_id: str) -> dict[str, Any]:
        row = self.repo.get_product(tenant_id=tenant_id, product_id=product_id)
        if row is None:
            raise ProductsError(code="NOT_FOUND", message="product_not_found", http_status=404)
        return product_to_dict(row)

    def create_product(self, *, tenant_id: str, body: ProductWriteBody) -> dict[str, Any]:
        self._validate_images(tenant_id=tenant_id, images=body.images)
        row = self.repo.create_product(
            tenant_id=tenant_id,
            fields={
                "name": body.name.strip(),
                "price": (body.price or "").strip() or None,
                "sizes": body.sizes,
                "colors": body.colors,
                "note": (body.note or "").strip() or None,
            },
        )
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
        self.session.expire(row, ["images", "links"])
        refreshed = self.repo.get_product(tenant_id=tenant_id, product_id=row.id)
        assert refreshed is not None
        return product_to_dict(refreshed)

    def update_product(
        self,
        *,
        tenant_id: str,
        product_id: str,
        body: ProductWriteBody,
    ) -> dict[str, Any]:
        row = self.repo.get_product(tenant_id=tenant_id, product_id=product_id)
        if row is None:
            raise ProductsError(code="NOT_FOUND", message="product_not_found", http_status=404)
        self._validate_images(tenant_id=tenant_id, images=body.images)
        self.repo.update_product(
            row,
            fields={
                "name": body.name.strip(),
                "price": (body.price or "").strip() or None,
                "sizes": body.sizes,
                "colors": body.colors,
                "note": (body.note or "").strip() or None,
            },
        )
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
        self.session.expire(row, ["images", "links"])
        refreshed = self.repo.get_product(tenant_id=tenant_id, product_id=row.id)
        assert refreshed is not None
        return product_to_dict(refreshed)

    def delete_product(self, *, tenant_id: str, product_id: str) -> list[str]:
        row = self.repo.get_product(tenant_id=tenant_id, product_id=product_id)
        if row is None:
            raise ProductsError(code="NOT_FOUND", message="product_not_found", http_status=404)
        media_ids = self.repo.delete_product(row)
        remove_product_from_index(tenant_id=tenant_id, product_id=product_id)
        return media_ids

    def preview_csv(self, *, csv_text: str) -> dict[str, Any]:
        """Validate import rows without persisting — 0 AI credits."""
        reader = csv.DictReader(io.StringIO(csv_text.strip()))
        if not reader.fieldnames or "name" not in {h.strip().lower() for h in reader.fieldnames}:
            raise ProductsError(
                code="INVALID_CSV",
                message="csv_must_include_name_column",
                http_status=400,
            )
        rows: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []
        valid_count = 0
        for idx, raw in enumerate(reader, start=2):
            normalized_row = {str(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
            name = normalized_row.get("name") or ""
            row_preview = {
                "row": idx,
                "name": name,
                "price": normalized_row.get("price") or None,
                "sizes": [s.strip() for s in (normalized_row.get("sizes") or "").split("|") if s.strip()],
                "colors": [c.strip() for c in (normalized_row.get("colors") or "").split("|") if c.strip()],
                "note": normalized_row.get("note") or None,
            }
            if not name:
                errors.append({"row": str(idx), "error": "missing_name"})
                row_preview["valid"] = False
            else:
                row_preview["valid"] = True
                valid_count += 1
            rows.append(row_preview)
        return {
            "preview": rows,
            "valid_count": valid_count,
            "error_count": len(errors),
            "errors": errors,
            "import_format": "csv_v1",
        }

    def import_csv(self, *, tenant_id: str, csv_text: str) -> dict[str, Any]:
        """Basic CSV import — name required; price/sizes/colors/note optional."""
        reader = csv.DictReader(io.StringIO(csv_text.strip()))
        if not reader.fieldnames or "name" not in {h.strip().lower() for h in reader.fieldnames}:
            raise ProductsError(
                code="INVALID_CSV",
                message="csv_must_include_name_column",
                http_status=400,
            )
        created = 0
        errors: list[dict[str, str]] = []
        for idx, raw in enumerate(reader, start=2):
            normalized_row = {str(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
            name = normalized_row.get("name") or ""
            if not name:
                errors.append({"row": str(idx), "error": "missing_name"})
                continue
            sizes = [s.strip() for s in (normalized_row.get("sizes") or "").split("|") if s.strip()]
            colors = [c.strip() for c in (normalized_row.get("colors") or "").split("|") if c.strip()]
            try:
                body = ProductWriteBody(
                    name=name,
                    price=normalized_row.get("price") or None,
                    sizes=sizes,
                    colors=colors,
                    note=normalized_row.get("note") or None,
                    images=[],
                    links=[],
                )
                self.create_product(tenant_id=tenant_id, body=body)
                created += 1
            except ProductsError as exc:
                errors.append({"row": str(idx), "error": exc.code})
            except ValueError as exc:
                errors.append({"row": str(idx), "error": str(exc)})
        return {"created": created, "errors": errors, "import_format": "csv_v1"}

    def _sync_image_index(self, *, tenant_id: str, product_id: str, images: list[Any]) -> None:
        for img in images:
            media_id = str(getattr(img, "media_id", "") or "")
            if media_id:
                upsert_product_image_index(
                    tenant_id=tenant_id,
                    product_id=product_id,
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
