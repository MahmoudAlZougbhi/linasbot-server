"""Pydantic schemas for tenant services with priced options."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


class ServiceOptionInput(BaseModel):
    id: str | None = None
    machine_name: str | None = Field(default=None, max_length=256)
    body_part: str | None = Field(default=None, max_length=256)
    staff_name: str | None = Field(default=None, max_length=256)
    price: str = Field(min_length=1, max_length=128)
    currency: str = Field(default="USD", min_length=1, max_length=16)
    sort_order: int = Field(default=0, ge=0)

    @field_validator("machine_name", "body_part", "staff_name")
    @classmethod
    def clean_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @field_validator("price")
    @classmethod
    def clean_price(cls, value: str) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("price_required")
        return text


class ServiceWriteBody(BaseModel):
    name: str = Field(min_length=1, max_length=512)
    active: bool = True
    options: list[ServiceOptionInput] = Field(min_length=1)

    @field_validator("options")
    @classmethod
    def validate_options(cls, value: list[ServiceOptionInput]) -> list[ServiceOptionInput]:
        if not value:
            raise ValueError("at_least_one_option_required")
        return value


def normalize_service_name(name: str) -> str:
    return " ".join(str(name or "").strip().lower().split())


def option_to_dict(row: Any) -> dict[str, Any]:
    return {
        "id": row.id,
        "machine_name": row.machine_name,
        "body_part": row.body_part,
        "staff_name": row.staff_name,
        "price": row.price,
        "currency": row.currency,
        "sort_order": row.sort_order,
    }


def service_to_dict(row: Any) -> dict[str, Any]:
    options = sorted(row.options or [], key=lambda o: o.sort_order)
    prices = [opt.price for opt in options if opt.price]
    return {
        "id": row.id,
        "name": row.name,
        "active": bool(row.active),
        "options": [option_to_dict(opt) for opt in options],
        "price_summary": _price_summary(options),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _price_summary(options: list[Any]) -> str | None:
    if not options:
        return None
    if len(options) == 1:
        opt = options[0]
        return f"{opt.price} {opt.currency}".strip()
    currencies = {opt.currency for opt in options}
    if len(currencies) == 1:
        currency = next(iter(currencies))
        return f"from {options[0].price} {currency}".strip()
    return f"{options[0].price} ({len(options)} options)"
