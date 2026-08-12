"""Token wallet models, exceptions, and unlimited-tenant helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

DEFAULT_UNLIMITED_TENANTS = frozenset({"linas"})

# One-time legacy split (documented; do not invent other ratios).
LEGACY_INPUT_SHARE = 0.80
LEGACY_OUTPUT_SHARE = 0.20
MIGRATION_NOTE = (
    "Migrated from legacy single balance_tokens: remaining split "
    f"{int(LEGACY_INPUT_SHARE * 100)}% input / {int(LEGACY_OUTPUT_SHARE * 100)}% output."
)


class InsufficientTokenBalance(Exception):
    """Raised when a metered tenant cannot cover an AI token debit."""

    def __init__(
        self,
        tenant_id: str,
        balance: int,
        required: int,
        *,
        bucket: str | None = None,
        input_remaining: int | None = None,
        output_remaining: int | None = None,
    ) -> None:
        self.tenant_id = tenant_id
        self.balance = balance
        self.required = required
        self.bucket = bucket
        self.input_remaining = input_remaining
        self.output_remaining = output_remaining
        detail = f"Insufficient token balance for tenant={tenant_id}"
        if bucket:
            detail += f" bucket={bucket}"
        detail += f" balance={balance} required={required}"
        super().__init__(detail)


def unlimited_tenant_ids() -> frozenset[str]:
    raw = (os.getenv("TOKEN_WALLET_UNLIMITED_TENANT_IDS") or "linas").strip()
    ids = {part.strip().lower() for part in raw.split(",") if part.strip()}
    return frozenset(ids or DEFAULT_UNLIMITED_TENANTS)


def normalize_wallet_tenant_id(tenant_id: str | None) -> str:
    """Normalize a request tenant_id; fail closed when missing or blank."""
    tid = str(tenant_id or "").strip().lower()
    if not tid:
        raise ValueError("tenant_id required")
    return tid


def is_unlimited_tenant(tenant_id: str | None) -> bool:
    tid = normalize_wallet_tenant_id(tenant_id)
    return tid in unlimited_tenant_ids()


@dataclass
class WalletSnapshot:
    tenant_id: str
    input_remaining: int
    output_remaining: int
    lifetime_input_credited: int
    lifetime_output_credited: int
    lifetime_input_debited: int
    lifetime_output_debited: int
    lifetime_spent_usd: float
    unlimited: bool
    updated_at: float
    migrated_from_legacy: bool = False

    @property
    def balance_tokens(self) -> int:
        return int(self.input_remaining) + int(self.output_remaining)

    @property
    def lifetime_credited(self) -> int:
        return int(self.lifetime_input_credited) + int(self.lifetime_output_credited)

    @property
    def lifetime_debited(self) -> int:
        return int(self.lifetime_input_debited) + int(self.lifetime_output_debited)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "input_remaining": self.input_remaining,
            "output_remaining": self.output_remaining,
            "input_used": self.lifetime_input_debited,
            "output_used": self.lifetime_output_debited,
            "lifetime_input_credited": self.lifetime_input_credited,
            "lifetime_output_credited": self.lifetime_output_credited,
            "lifetime_input_debited": self.lifetime_input_debited,
            "lifetime_output_debited": self.lifetime_output_debited,
            "lifetime_spent_usd": round(self.lifetime_spent_usd, 6),
            # Legacy-compatible totals (sum of both buckets).
            "balance_tokens": self.balance_tokens,
            "lifetime_credited": self.lifetime_credited,
            "lifetime_debited": self.lifetime_debited,
            "tokens_used": self.lifetime_debited,
            "tokens_remaining": self.balance_tokens,
            "unlimited": self.unlimited,
            "updated_at": self.updated_at,
            "migrated_from_legacy": self.migrated_from_legacy,
            "policy": (
                "AI pauses when either the input or output balance is empty. "
                "Each AI call debits prompt tokens from input and completion tokens from output."
            ),
        }
