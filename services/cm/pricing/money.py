"""Decimal-safe money helpers for the pricing engine.

JSON/API payloads may still carry floats; all arithmetic runs on Decimal and is
quantized before leaving the engine. Notes and free text never affect amounts.
"""

from __future__ import annotations

from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal
from typing import SupportsFloat

from services.cm.pricing.schemas import RoundingPolicy

MoneyLike = Decimal | float | int | str | SupportsFloat | None

_TWO = Decimal("0.01")
_ONE = Decimal("1")


def as_money(value: MoneyLike, *, default: Decimal | None = None) -> Decimal:
    if value is None:
        if default is not None:
            return default
        raise ValueError("money value is required")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def money_to_float(value: Decimal) -> float:
    """Serialize quantized Decimal for JSON/API without binary float drift on round-trip inputs."""
    return float(value)


def quantize_money(value: Decimal, policy: RoundingPolicy) -> Decimal:
    if policy == "none":
        return value
    if policy == "nearest_1":
        return value.quantize(_ONE, rounding=ROUND_HALF_UP)
    if policy == "floor_0_01":
        return value.quantize(_TWO, rounding=ROUND_FLOOR)
    if policy == "ceil_0_01":
        return value.quantize(_TWO, rounding=ROUND_CEILING)
    return value.quantize(_TWO, rounding=ROUND_HALF_UP)
