"""Integer money and credit units — never binary floats for financial truth.

Conversions (frozen product rules):
  1 credit = $0.001 actual provider cost
  1 credit = 1_000 millicredits = 1_000 micro-USD
  1 millicredit = 1 micro-USD
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Final

MICRO_USD_PER_USD: Final[int] = 1_000_000
MILLICREDITS_PER_CREDIT: Final[int] = 1_000
MICRO_USD_PER_CREDIT: Final[int] = 1_000  # $0.001
MICRO_USD_PER_MILLICREDIT: Final[int] = 1

# Top-up commercial rule: 500 credits per $1 → 500_000 millicredits per $1
TOPUP_CREDITS_PER_USD: Final[int] = 500
TOPUP_MILLICREDITS_PER_MICRO_USD: Final[int] = (
    TOPUP_CREDITS_PER_USD * MILLICREDITS_PER_CREDIT
) // MICRO_USD_PER_USD  # 0.5 millicredit per micro-USD


class MoneyError(ValueError):
    """Invalid money/credit conversion input."""


def _as_decimal(value: Decimal | int | str | float) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, str):
        return Decimal(value)
    # float accepted only at system boundaries; convert via str to avoid binary drift
    return Decimal(str(value))


def usd_to_micro_usd(usd: Decimal | int | str | float) -> int:
    """Round once to nearest micro-USD (conservative HALF_UP)."""
    d = _as_decimal(usd)
    if d < 0:
        raise MoneyError("USD amount cannot be negative")
    micros = (d * Decimal(MICRO_USD_PER_USD)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(micros)


def micro_usd_to_millicredits(micro_usd: int) -> int:
    """1 micro-USD = 1 millicredit (exact integer identity)."""
    if micro_usd < 0:
        raise MoneyError("micro-USD cannot be negative")
    return int(micro_usd)


def millicredits_to_credits_display(millicredits: int, *, places: int = 3) -> str:
    """UI may show up to three decimal credit places."""
    if places < 0 or places > 6:
        raise MoneyError("places out of range")
    q = Decimal(10) ** places
    credits = (Decimal(millicredits) / Decimal(MILLICREDITS_PER_CREDIT)).quantize(
        Decimal(1) / q, rounding=ROUND_HALF_UP
    )
    return format(credits, f".{places}f")


def credits_to_millicredits(credits: Decimal | int | str | float) -> int:
    d = _as_decimal(credits)
    if d < 0:
        raise MoneyError("credits cannot be negative")
    mc = (d * Decimal(MILLICREDITS_PER_CREDIT)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(mc)


def provider_cost_usd_to_millicredits(cost_usd: Decimal | int | str | float) -> int:
    """Actual provider cost → millicredits via micro-USD identity (no margin markup)."""
    return micro_usd_to_millicredits(usd_to_micro_usd(cost_usd))


def topup_usd_to_purchased_millicredits(pack_usd: Decimal | int | str | float) -> int:
    """500 credits per $1 of pack price."""
    dollars = _as_decimal(pack_usd)
    if dollars <= 0:
        raise MoneyError("top-up pack price must be positive")
    credits = dollars * Decimal(TOPUP_CREDITS_PER_USD)
    return credits_to_millicredits(credits)


@dataclass(frozen=True)
class CostBreakdownMicroUsd:
    input_uncached_micro_usd: int
    input_cached_micro_usd: int
    cache_write_micro_usd: int
    output_micro_usd: int
    tool_micro_usd: int
    other_micro_usd: int

    @property
    def total_micro_usd(self) -> int:
        return (
            self.input_uncached_micro_usd
            + self.input_cached_micro_usd
            + self.cache_write_micro_usd
            + self.output_micro_usd
            + self.tool_micro_usd
            + self.other_micro_usd
        )

    @property
    def total_millicredits(self) -> int:
        return micro_usd_to_millicredits(self.total_micro_usd)
