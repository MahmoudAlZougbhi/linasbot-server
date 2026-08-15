"""Pydantic schemas for AI Products API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from services.products.availability import AVAILABILITY_IN_STOCK, normalize_availability

MAX_IMAGES = 3


class ProductImageInput(BaseModel):
    media_id: str = Field(min_length=1, max_length=64)
    sort_order: int = Field(ge=0, lt=MAX_IMAGES)


class ProductLinkInput(BaseModel):
    url: str = Field(min_length=1)
    label: str | None = Field(default=None, max_length=256)
    sort_order: int = Field(default=0, ge=0)


class ProductWriteBody(BaseModel):
    name: str = Field(min_length=1, max_length=512)
    price: str | None = Field(default=None, max_length=128)
    sizes: list[str] = Field(default_factory=list)
    colors: list[str] = Field(default_factory=list)
    note: str | None = None
    availability: str = Field(default=AVAILABILITY_IN_STOCK, max_length=32)
    images: list[ProductImageInput] = Field(default_factory=list)
    links: list[ProductLinkInput] = Field(default_factory=list)

    @field_validator("availability")
    @classmethod
    def validate_availability(cls, value: str) -> str:
        return normalize_availability(value)

    @field_validator("images")
    @classmethod
    def validate_images(cls, value: list[ProductImageInput]) -> list[ProductImageInput]:
        if len(value) > MAX_IMAGES:
            raise ValueError(f"max_{MAX_IMAGES}_images")
        media_ids = [row.media_id for row in value]
        if len(media_ids) != len(set(media_ids)):
            raise ValueError("duplicate_media_id")
        sort_orders = [row.sort_order for row in value]
        if len(sort_orders) != len(set(sort_orders)):
            raise ValueError("duplicate_sort_order")
        return value

    @field_validator("sizes", "colors")
    @classmethod
    def clean_string_lists(cls, value: list[str]) -> list[str]:
        out: list[str] = []
        for item in value:
            text = str(item or "").strip()
            if text:
                out.append(text[:128])
        return out


class ProductImportBody(BaseModel):
    csv_text: str = Field(min_length=1)


class ProductXlsxImportBody(BaseModel):
    file_base64: str = Field(min_length=1)


def normalize_product_name(name: str) -> str:
    return " ".join(str(name or "").strip().lower().split())


def product_to_dict(row: Any) -> dict[str, Any]:
    availability = normalize_availability(getattr(row, "availability", None))
    return {
        "id": row.id,
        "name": row.name,
        "price": row.price,
        "sizes": list(row.sizes or []),
        "colors": list(row.colors or []),
        "note": row.note,
        "availability": availability,
        "images": [
            {"id": img.id, "media_id": img.media_id, "sort_order": img.sort_order}
            for img in sorted(row.images or [], key=lambda i: i.sort_order)
        ],
        "links": [
            {
                "id": link.id,
                "url": link.url,
                "label": link.label,
                "sort_order": link.sort_order,
            }
            for link in sorted(row.links or [], key=lambda l: l.sort_order)
        ],
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }
