"""ASSN V2 effect handlers (refund / consumption / typed apply).

Kept separate from ``apple_iap_processor`` so the processor stays under the
500-line source cap.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from db.models.apple_billing import AppleCreditGrantRow
from db.session import whatsapp_session
from services import apple_transaction_ledger as txn_ledger
from services.apple_app_store_client import apple_app_store_client, iap_credentials_configured
from services.apple_iap_effects import (
    apply_subscription_effect,
    bump_entitlement_period_from_expires,
    classify_product,
    grant_consumable_credits,
    lookup_tenant_by_app_account_token,
    reverse_consumable_credits,
)
from services.entitlements_service import EntitlementStatus
from services.iap_product_catalog import is_credit_product

logger = logging.getLogger(__name__)


def resolve_tenant(
    *,
    tenant_id: str | None,
    payload: dict[str, Any],
    source: str,
) -> tuple[str, str | None]:
    token = str(payload.get("appAccountToken") or "").strip()
    mapped = lookup_tenant_by_app_account_token(token) if token else None
    client_sources = {"client_verify", "client_restore"}
    if source in client_sources:
        if not mapped:
            raise PermissionError("appAccountToken required for client purchase verification")
        if tenant_id and mapped[0] != str(tenant_id).strip():
            raise PermissionError("appAccountToken belongs to a different tenant")
        return mapped[0], mapped[1]
    if tenant_id:
        tid = str(tenant_id).strip()
        if mapped and mapped[0] != tid:
            raise PermissionError("appAccountToken belongs to a different tenant")
        return tid, (mapped[1] if mapped else None)
    if mapped:
        return mapped[0], mapped[1]
    raise ValueError("tenant_id required (pass explicitly or set appAccountToken)")


def handle_refund_or_revoke(
    *,
    payload: dict[str, Any],
    tenant_id: str | None,
    notification_type: str,
) -> dict[str, Any]:
    product_id = str(payload.get("productId") or "").strip()
    transaction_id = str(payload.get("transactionId") or "").strip()
    original_transaction_id = str(payload.get("originalTransactionId") or transaction_id).strip()
    tid, _ = resolve_tenant(tenant_id=tenant_id, payload=payload, source="assn")
    status: Literal["refunded", "revoked"] = "refunded" if notification_type == "REFUND" else "revoked"
    out: dict[str, Any] = {"notification_type": notification_type, "tenant_id": tid}
    if is_credit_product(product_id):
        out["credit_reverse"] = reverse_consumable_credits(
            tenant_id=tid,
            transaction_id=transaction_id,
            product_id=product_id,
        )
        try:
            txn_ledger.mark_reversed(transaction_id, effect=out["credit_reverse"])
        except ValueError:
            pass
    else:
        out["subscription"] = apply_subscription_effect(
            tenant_id=tid,
            product_id=product_id,
            original_transaction_id=original_transaction_id,
            status=status,
            idempotency_key=f"apple:notify:{notification_type}:{transaction_id}",
        )
    return out


def handle_refund_reversed(
    *,
    payload: dict[str, Any],
    tenant_id: str | None,
) -> dict[str, Any]:
    """Re-apply credits or subscription after Apple REFUND_REVERSED."""
    product_id = str(payload.get("productId") or "").strip()
    transaction_id = str(payload.get("transactionId") or "").strip()
    original_transaction_id = str(payload.get("originalTransactionId") or transaction_id).strip()
    tid, _ = resolve_tenant(tenant_id=tenant_id, payload=payload, source="assn")
    out: dict[str, Any] = {"notification_type": "REFUND_REVERSED", "tenant_id": tid}
    if is_credit_product(product_id):
        out["credit_restore"] = grant_consumable_credits(
            tenant_id=tid,
            product_id=product_id,
            transaction_id=transaction_id,
            allow_regrant_after_reverse=True,
        )
        try:
            txn_ledger.mark_applied(transaction_id, effect=out["credit_restore"])
        except ValueError:
            pass
    else:
        out["subscription"] = apply_subscription_effect(
            tenant_id=tid,
            product_id=product_id,
            original_transaction_id=original_transaction_id,
            status="active",
            idempotency_key=f"apple:notify:REFUND_REVERSED:{transaction_id}",
        )
    return out


def handle_consumption_request(
    *,
    payload: dict[str, Any] | None,
    related_transaction_id: str | None,
) -> dict[str, Any]:
    """Respond to ASSN CONSUMPTION_REQUEST via App Store Server API when configured."""
    tid = str((payload or {}).get("transactionId") or related_transaction_id or "").strip()
    if not tid:
        return {"ack": "consumption_request", "sent": False, "reason": "missing_transaction_id"}
    if not iap_credentials_configured():
        return {"ack": "consumption_request", "sent": False, "reason": "iap_credentials_missing"}

    with whatsapp_session() as session:
        grant = session.get(AppleCreditGrantRow, tid)
    # Apple consumption statuses: 0 undeclared, 1 not consumed, 2 partially, 3 fully.
    if grant is None:
        consumption_status = 0
        delivery_status = 0
    elif grant.status == "reversed":
        consumption_status = 1
        delivery_status = 1
    else:
        consumption_status = 3
        delivery_status = 1
    body = {
        "customerConsented": True,
        "consumptionStatus": consumption_status,
        "platform": 1,  # Apple
        "sampleContentProvided": False,
        "deliveryStatus": delivery_status,
    }
    try:
        apple_app_store_client.send_consumption_info(tid, body)
        return {"ack": "consumption_request", "sent": True, "transaction_id": tid, "body": body}
    except Exception as exc:  # noqa: BLE001 — fail-soft; ASSN must still ACK
        logger.warning("apple_consumption_info_failed tid=%s err=%s", tid, exc)
        return {
            "ack": "consumption_request",
            "sent": False,
            "transaction_id": tid,
            "error": str(exc)[:200],
        }


def handle_metadata_only(
    *,
    notification_type: str,
    subtype: str | None,
    renewal: dict[str, Any] | None,
) -> dict[str, Any]:
    """PRICE_INCREASE / RENEWAL_EXTENDED / DID_CHANGE_RENEWAL_PREF — no status→active."""
    return {
        "notification_type": notification_type,
        "subtype": subtype,
        "effect_kind": "metadata_only",
        "status": None,
        "renewal": renewal,
    }


def handle_consumable_only(
    *,
    process_signed_transaction_fn: Any,
    signed_transaction_jws: str,
    txn_payload: dict[str, Any],
    notification_type: str,
) -> dict[str, Any]:
    """ONE_TIME_CHARGE: consumable credit path only — never activate a subscription."""
    product_id = str(txn_payload.get("productId") or "").strip()
    kind = classify_product(product_id)
    if kind != "consumable":
        return {
            "skipped": True,
            "reason": "one_time_charge_not_consumable",
            "product_id": product_id,
            "kind": kind,
            "status": None,
        }
    return process_signed_transaction_fn(
        signed_transaction_jws=signed_transaction_jws,
        tenant_id=None,
        source=f"assn:{notification_type}",
        notification_type=notification_type,
        decoded_payload=txn_payload,
        skip_jws_verify=True,
    )


def handle_apply_txn(
    *,
    process_signed_transaction_fn: Any,
    signed_transaction_jws: str,
    txn_payload: dict[str, Any],
    notification_type: str,
    status: EntitlementStatus | None,
) -> dict[str, Any]:
    """Apply subscription/credit effect using classified status (never invent active).

    Activating events reuse ``process_signed_transaction`` (txn idempotency).
    Non-activating lifecycle (grace/expired/canceled) applies entitlement status
    even when the Apple transaction row is already ``applied``.
    """
    if status is None:
        return {
            "skipped": True,
            "reason": "no_status_change",
            "notification_type": notification_type,
            "status": None,
        }
    if status == "active":
        return process_signed_transaction_fn(
            signed_transaction_jws=signed_transaction_jws,
            tenant_id=None,
            source=f"assn:{notification_type}",
            notification_type=notification_type,
            decoded_payload=txn_payload,
            skip_jws_verify=True,
        )

    product_id = str(txn_payload.get("productId") or "").strip()
    transaction_id = str(txn_payload.get("transactionId") or "").strip()
    original_transaction_id = str(txn_payload.get("originalTransactionId") or transaction_id).strip()
    if not product_id or not transaction_id:
        raise ValueError("transaction payload missing productId/transactionId")
    kind = classify_product(product_id)
    if kind != "subscription":
        return {
            "skipped": True,
            "reason": "lifecycle_not_subscription",
            "kind": kind,
            "status": status,
        }
    tid, _ = resolve_tenant(tenant_id=None, payload=txn_payload, source="assn")
    txn_ledger.upsert_transaction(
        txn_payload,
        signed_jws=signed_transaction_jws or None,
        tenant_id=tid,
        user_id=None,
    )
    effect = apply_subscription_effect(
        tenant_id=tid,
        product_id=product_id,
        original_transaction_id=original_transaction_id,
        status=status,
        idempotency_key=f"apple:notify:{notification_type}:{transaction_id}:{status}",
    )
    expires = txn_payload.get("expiresDate")
    try:
        bump_entitlement_period_from_expires(
            tenant_id=tid,
            expires_date_ms=int(expires) if expires is not None else None,
        )
    except (TypeError, ValueError):
        pass
    return {
        "ok": True,
        "tenant_id": tid,
        "transaction_id": transaction_id,
        "kind": kind,
        "status": status,
        "effect": effect,
    }
