"""Verified-purchase message grants are not a live meter. IAP credits grant the ledger.

Retired Stripe `linas_token_pack` metadata is skip-only (`token_pack_retired`).
"""

from __future__ import annotations

from typing import Any

from services.billing.membership.message_ledger import revoke_purchased

STRIPE_TOKEN_PRODUCT = "linas_token_pack"
STRIPE_MESSAGE_PRODUCT = "linas_message_pack"


def grant_from_mapped_pack(
    *,
    tenant_id: str,
    transaction_id: str,
    pack: dict[str, Any] | None,
) -> dict[str, Any]:
    _ = tenant_id, transaction_id, pack
    return {"granted": False, "reason": "credits_meter_only"}


def maybe_grant_purchased_from_verified_txn(
    *,
    tenant_id: str,
    product_id: str,
    transaction_id: str,
) -> dict[str, Any]:
    _ = tenant_id, product_id, transaction_id
    return {"granted": False, "reason": "credits_meter_only"}


def maybe_revoke_purchased_from_verified_txn(
    *,
    tenant_id: str,
    transaction_id: str,
) -> dict[str, Any]:
    result = revoke_purchased(tenant_id=tenant_id, transaction_id=transaction_id)
    if not result.get("revoked"):
        return {"revoked": False, "reason": "no_purchased_lot"}
    return {"revoked": True, **result}


def stripe_checkout_kind(metadata: dict[str, Any] | None) -> str:
    product = str((metadata or {}).get("product") or "")
    if product == STRIPE_TOKEN_PRODUCT:
        return "token_pack"
    if product == STRIPE_MESSAGE_PRODUCT:
        return "message_pack"
    return "unknown"


def apply_verified_stripe_message_checkout(
    *,
    tenant_id: str,
    product_id: str,
    transaction_id: str,
) -> dict[str, Any]:
    return maybe_grant_purchased_from_verified_txn(
        tenant_id=tenant_id,
        product_id=product_id,
        transaction_id=transaction_id,
    )
