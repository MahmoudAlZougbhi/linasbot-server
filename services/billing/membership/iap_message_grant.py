"""Verified-purchase message grants. Historical credit SKUs stay Apple product ids."""

from __future__ import annotations

from typing import Any

from services.billing.membership.message_ledger import grant_purchased, revoke_purchased

STRIPE_TOKEN_PRODUCT = "linas_token_pack"
STRIPE_MESSAGE_PRODUCT = "linas_message_pack"


def _pack_for_product(product_id: str) -> dict[str, Any] | None:
    pid = (product_id or "").strip()
    if not pid:
        return None
    from services.billing.membership.catalog_admin import current_catalog, published_sale_ready_pack
    from services.billing.membership.economy_policy import load_economy

    published = published_sale_ready_pack(pid)
    if published:
        return published
    catalog = current_catalog()
    for pack in catalog.get("topup_packs") or []:
        if str(pack.get("product_id") or "") != pid:
            continue
        qty = int(pack.get("quantity") or 0)
        if qty > 0:
            return {"pack_id": str(pack.get("pack_id") or pid), "quantity": qty, **dict(pack)}
    qty = load_economy()["iap_message_quantities"].get(pid)
    if qty:
        return {"pack_id": pid, "quantity": int(qty), "product_id": pid}
    return None


def grant_from_mapped_pack(
    *,
    tenant_id: str,
    transaction_id: str,
    pack: dict[str, Any] | None,
) -> dict[str, Any]:
    if not pack:
        return {"granted": False, "reason": "pack_unmapped"}
    qty = int(pack.get("quantity") or 0)
    if qty <= 0:
        return {"granted": False, "reason": "pack_unmapped"}
    tid = tenant_id.strip()
    txn = transaction_id.strip()
    pack_id = str(pack.get("pack_id") or "messages")
    lot = grant_purchased(
        tenant_id=tid,
        lot_id=f"{tid}:{pack_id}:{txn}",
        amount=qty,
        source_transaction_id=txn,
    )
    return {"granted": True, "messages": qty, "lot_id": lot.lot_id, "transaction_id": txn}


def maybe_grant_purchased_from_verified_txn(
    *,
    tenant_id: str,
    product_id: str,
    transaction_id: str,
) -> dict[str, Any]:
    return grant_from_mapped_pack(
        tenant_id=tenant_id,
        transaction_id=transaction_id,
        pack=_pack_for_product(product_id),
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
    return maybe_grant_purchased_from_verified_txn(
        tenant_id=tenant_id,
        product_id=product_id,
        transaction_id=transaction_id,
    )
