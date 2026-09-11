"""Verified-purchase message grants. Never convert credit SKUs to messages."""

from __future__ import annotations

from typing import Any

from services.membership.catalog_admin import published_sale_ready_pack
from services.membership.message_flags import message_billing_cutover
from services.membership.message_ledger import grant_purchased, revoke_purchased

STRIPE_TOKEN_PRODUCT = "linas_token_pack"
STRIPE_MESSAGE_PRODUCT = "linas_message_pack"


def grant_from_mapped_pack(
    *,
    tenant_id: str,
    transaction_id: str,
    pack: dict[str, Any] | None,
) -> dict[str, Any]:
    tid = (tenant_id or "").strip()
    txn = (transaction_id or "").strip()
    if not tid or not txn:
        return {"granted": False, "reason": "missing_transaction"}
    if not pack or not pack.get("sale_ready") or pack.get("price_usd") in (None, ""):
        return {"granted": False, "reason": "pack_not_sale_ready"}
    quantity = int(pack.get("quantity") or 0)
    if quantity <= 0:
        return {"granted": False, "reason": "pack_not_sale_ready"}
    pack_id = str(pack.get("pack_id") or "messages")
    lot = grant_purchased(
        tenant_id=tid,
        lot_id=f"{tid}:{pack_id}:{txn}",
        amount=quantity,
        source_transaction_id=txn,
    )
    return {
        "granted": True,
        "lot_id": lot.lot_id,
        "amount": quantity,
        "pack_id": pack_id,
    }


def maybe_grant_purchased_from_verified_txn(
    *,
    tenant_id: str,
    product_id: str,
    transaction_id: str,
) -> dict[str, Any]:
    if not message_billing_cutover():
        return {"granted": False, "reason": "cutover_off"}
    pack = published_sale_ready_pack(product_id)
    if pack is None:
        return {"granted": False, "reason": "unmapped_or_unpriced_pack"}
    return grant_from_mapped_pack(
        tenant_id=tenant_id,
        transaction_id=transaction_id,
        pack=pack,
    )


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
    """Grant only a mapped sale-ready pack. Never credit token wallets."""
    return maybe_grant_purchased_from_verified_txn(
        tenant_id=tenant_id,
        product_id=product_id,
        transaction_id=transaction_id,
    )
