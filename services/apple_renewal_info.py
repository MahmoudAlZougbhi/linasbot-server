"""Decode ASSN ``signedRenewalInfo`` and apply grace / cancel / price metadata.

Mere presence of renewal info must never force entitlement ``active``.
"""

from __future__ import annotations

import time
from typing import Any

from services.apple_iap_effects import (
    apply_subscription_effect,
    lookup_tenant_by_app_account_token,
)
from services.apple_jws import decode_jws_payload
from services.entitlements_service import EntitlementStatus, entitlements_store
from services.iap_product_catalog import is_subscription_product
from services.subscription_downgrade import (
    is_downgrade,
    schedule_pending_downgrade,
)


def _ms_to_epoch(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(int(value)) / 1000.0
    except (TypeError, ValueError):
        return None


def _resolve_tenant_id(
    tenant_id: str | None,
    txn_payload: dict[str, Any],
) -> str | None:
    if tenant_id and str(tenant_id).strip():
        return str(tenant_id).strip()
    token = str(txn_payload.get("appAccountToken") or "").strip()
    if not token:
        return None
    mapped = lookup_tenant_by_app_account_token(token)
    return mapped[0] if mapped else None


def decode_and_apply_renewal_info(
    signed_renewal_jws: str,
    *,
    tenant_id: str | None,
    notification_type: str,
    subtype: str | None,
    txn_payload: dict[str, Any],
) -> dict[str, Any]:
    """Verify renewal JWS and apply grace/cancel/price lifecycle hints only.

    Never treats presence of ``signedRenewalInfo`` as an activating event.
    """
    renewal = decode_jws_payload(signed_renewal_jws)
    auto_renew_status = renewal.get("autoRenewStatus")
    try:
        auto_renew_int = int(auto_renew_status) if auto_renew_status is not None else None
    except (TypeError, ValueError):
        auto_renew_int = None

    grace_expires_ms = renewal.get("gracePeriodExpiresDate")
    in_billing_retry = renewal.get("isInBillingRetryPeriod")
    price_increase_status = renewal.get("priceIncreaseStatus")
    expiration_intent = renewal.get("expirationIntent")
    renewal_date_ms = renewal.get("renewalDate")
    auto_renew_product_id = renewal.get("autoRenewProductId")

    info = {
        "autoRenewStatus": auto_renew_int,
        "autoRenewProductId": str(auto_renew_product_id).strip() if auto_renew_product_id else None,
        "gracePeriodExpiresDate": grace_expires_ms,
        "isInBillingRetryPeriod": bool(in_billing_retry) if in_billing_retry is not None else None,
        "priceIncreaseStatus": price_increase_status,
        "expirationIntent": expiration_intent,
        "renewalDate": renewal_date_ms,
    }

    hints: dict[str, Any] = {
        "notification_type": (notification_type or "").upper(),
        "subtype": (subtype or "").strip() or None,
    }
    # Lifecycle from renewal fields — never "active" from presence alone.
    lifecycle: str | None = None
    now_ms = int(time.time() * 1000)
    grace_ms: int | None
    try:
        grace_ms = int(grace_expires_ms) if grace_expires_ms is not None else None
    except (TypeError, ValueError):
        grace_ms = None

    if in_billing_retry is True or (grace_ms is not None and grace_ms > now_ms):
        lifecycle = "grace"
    elif auto_renew_int == 0:
        lifecycle = "canceled"
    if price_increase_status is not None:
        hints["price_increase_status"] = price_increase_status
    if expiration_intent is not None:
        hints["expiration_intent"] = expiration_intent
    if lifecycle:
        hints["lifecycle"] = lifecycle

    effect: dict[str, Any] | None = None
    tid = _resolve_tenant_id(tenant_id, txn_payload)
    product_id = str(auto_renew_product_id or txn_payload.get("productId") or "").strip()
    original_transaction_id = str(
        renewal.get("originalTransactionId")
        or txn_payload.get("originalTransactionId")
        or txn_payload.get("transactionId")
        or ""
    ).strip()

    status_to_apply: EntitlementStatus | None = None
    if lifecycle == "grace":
        status_to_apply = "grace"
    elif lifecycle == "canceled":
        status_to_apply = "canceled"

    if tid and status_to_apply and product_id and original_transaction_id and is_subscription_product(product_id):
        ntype = (notification_type or "RENEWAL_INFO").upper()
        effect = apply_subscription_effect(
            tenant_id=tid,
            product_id=product_id,
            original_transaction_id=original_transaction_id,
            status=status_to_apply,
            idempotency_key=f"apple:renewal:{ntype}:{original_transaction_id}:{status_to_apply}",
            notification_type=notification_type,
        )
        period_end = _ms_to_epoch(grace_ms if status_to_apply == "grace" else renewal_date_ms)
        if period_end is not None:
            ent = entitlements_store.get(tid)
            if ent.status in {"active", "trial", "grace", "canceled"}:
                ent.current_period_end = period_end
                entitlements_store.save(ent)
                effect = {**effect, "current_period_end": period_end}

    pending_downgrade: dict[str, Any] | None = None
    renew_product = str(auto_renew_product_id or "").strip()
    if tid and renew_product and is_subscription_product(renew_product):
        from services.iap_product_catalog import map_subscription_product

        try:
            renew_plan = map_subscription_product(renew_product)
        except ValueError:
            renew_plan = None
        ent = entitlements_store.get(tid)
        if renew_plan and is_downgrade(ent.plan_id, renew_plan):
            effective = _ms_to_epoch(renewal_date_ms) or ent.current_period_end
            pending_downgrade = schedule_pending_downgrade(
                tenant_id=tid,
                pending_plan_id=renew_plan,
                effective_at=effective,
            )
            if effect is None:
                effect = {"scheduled_downgrade": True, "pending_downgrade": pending_downgrade}
            else:
                effect = {**effect, "pending_downgrade": pending_downgrade}

    return {
        "renewal_info": info,
        "hints": hints,
        "tenant_id": tid,
        "effect": effect,
        "pending_downgrade": pending_downgrade,
        # Explicit: decoding renewal info is never an activating event by itself.
        "forced_active": False,
    }
