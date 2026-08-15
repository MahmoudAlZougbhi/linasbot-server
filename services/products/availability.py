"""Product availability states for AI Products catalog."""

from __future__ import annotations

from typing import Literal, cast

Availability = Literal["in_stock", "out_of_stock", "inactive"]

AVAILABILITY_IN_STOCK: Availability = "in_stock"
AVAILABILITY_OUT_OF_STOCK: Availability = "out_of_stock"
AVAILABILITY_INACTIVE: Availability = "inactive"

CUSTOMER_SEARCH_AVAILABILITY = frozenset({AVAILABILITY_IN_STOCK, AVAILABILITY_OUT_OF_STOCK})
ALL_AVAILABILITY = frozenset({AVAILABILITY_IN_STOCK, AVAILABILITY_OUT_OF_STOCK, AVAILABILITY_INACTIVE})

_ALIASES = {
    "in stock": AVAILABILITY_IN_STOCK,
    "instock": AVAILABILITY_IN_STOCK,
    "available": AVAILABILITY_IN_STOCK,
    "active": AVAILABILITY_IN_STOCK,
    "out of stock": AVAILABILITY_OUT_OF_STOCK,
    "outofstock": AVAILABILITY_OUT_OF_STOCK,
    "oos": AVAILABILITY_OUT_OF_STOCK,
    "unavailable": AVAILABILITY_OUT_OF_STOCK,
    "inactive": AVAILABILITY_INACTIVE,
    "hidden": AVAILABILITY_INACTIVE,
    "disabled": AVAILABILITY_INACTIVE,
}


def normalize_availability(raw: str | None, *, default: Availability = AVAILABILITY_IN_STOCK) -> Availability:
    text = str(raw or "").strip().lower().replace("_", " ").replace("-", " ")
    if not text:
        return default
    if text in ALL_AVAILABILITY:
        return cast(Availability, text)
    compact = text.replace(" ", "")
    if compact in ALL_AVAILABILITY:
        return cast(Availability, compact)
    return _ALIASES.get(text, _ALIASES.get(compact, default))


def is_customer_searchable(availability: str | None) -> bool:
    return normalize_availability(availability) in CUSTOMER_SEARCH_AVAILABILITY
