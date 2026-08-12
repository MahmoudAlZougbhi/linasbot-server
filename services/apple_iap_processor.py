"""Core Apple IAP authority: signed transactions + ASSN V2 + reconcile."""

from __future__ import annotations

import logging
import time
from typing import Any, Literal

from db.models.apple_billing import AppleNotificationEventRow
from db.session import whatsapp_session
from services import apple_transaction_ledger as txn_ledger
from services.apple_app_store_client import (
    AppleIapConfigError,
    apple_app_store_client,
    iap_credentials_configured,
)
from services.apple_iap_effects import (
    apply_subscription_effect,
    bump_entitlement_period_from_expires,
    classify_product,
    grant_consumable_credits,
    lookup_tenant_by_app_account_token,
    reverse_consumable_credits,
    subscription_status_from_payload,
)
from services.apple_jws import AppleJwsError, decode_jws_payload, sha256_hex
from services.iap_product_catalog import is_credit_product

logger = logging.getLogger(__name__)

_SKIP_NOTIFY_TYPES = frozenset({"TEST", "CONSUMPTION_REQUEST"})


class AppleIapProcessorError(RuntimeError):
    """Processing failure (config, tenant, or payload)."""


def _resolve_tenant(
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
    raise AppleIapProcessorError("tenant_id required (pass explicitly or set appAccountToken)")


def process_signed_transaction(
    *,
    signed_transaction_jws: str,
    tenant_id: str | None = None,
    user_id: str | None = None,
    source: str = "client_verify",
    notification_type: str | None = None,
    skip_jws_verify: bool = False,
    decoded_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Verify (unless pre-decoded), upsert ledger, apply subscription or credits once."""
    if decoded_payload is not None:
        payload = decoded_payload
    elif skip_jws_verify:
        raise AppleIapProcessorError("decoded_payload required when skip_jws_verify")
    else:
        payload = decode_jws_payload(signed_transaction_jws)

    tid_resolved, token_user = _resolve_tenant(tenant_id=tenant_id, payload=payload, source=source)
    uid = user_id or token_user or None
    product_id = str(payload.get("productId") or "").strip()
    transaction_id = str(payload.get("transactionId") or "").strip()
    original_transaction_id = str(payload.get("originalTransactionId") or transaction_id).strip()
    if not product_id or not transaction_id:
        raise AppleIapProcessorError("transaction payload missing productId/transactionId")

    row = txn_ledger.upsert_transaction(
        payload,
        signed_jws=signed_transaction_jws or None,
        tenant_id=tid_resolved,
        user_id=uid,
    )
    if row.processing_status == "applied":
        return {
            "ok": True,
            "duplicate": True,
            "transaction_id": transaction_id,
            "tenant_id": tid_resolved,
            "effect": row.effect or {},
        }
    if row.processing_status == "reversed":
        return {
            "ok": True,
            "duplicate": True,
            "reversed": True,
            "transaction_id": transaction_id,
            "tenant_id": tid_resolved,
            "effect": row.effect or {},
        }

    kind = classify_product(product_id)
    if kind == "subscription":
        status = subscription_status_from_payload(payload, notification_type=notification_type)
        if payload.get("revocationDate"):
            status = "revoked"
        effect = apply_subscription_effect(
            tenant_id=tid_resolved,
            product_id=product_id,
            original_transaction_id=original_transaction_id,
            status=status,
            idempotency_key=f"apple:txn:{transaction_id}:{status}",
        )
        expires = payload.get("expiresDate")
        try:
            bump_entitlement_period_from_expires(
                tenant_id=tid_resolved,
                expires_date_ms=int(expires) if expires is not None else None,
            )
        except (TypeError, ValueError):
            pass
    else:
        effect = grant_consumable_credits(
            tenant_id=tid_resolved,
            product_id=product_id,
            transaction_id=transaction_id,
        )

    txn_ledger.mark_applied(
        transaction_id,
        effect={"source": source, "kind": kind, **{k: v for k, v in effect.items() if k != "entitlement"}},
    )
    return {
        "ok": True,
        "duplicate": bool(effect.get("duplicate")),
        "transaction_id": transaction_id,
        "tenant_id": tid_resolved,
        "kind": kind,
        "effect": effect,
    }


def _record_notification(
    *,
    notification_uuid: str,
    notification_type: str,
    subtype: str | None,
    environment: str,
    signed_payload_sha256: str,
    processing_status: str,
    result: dict[str, Any],
    related_transaction_id: str | None,
) -> dict[str, Any]:
    now = time.time()
    with whatsapp_session() as session:
        row = session.get(AppleNotificationEventRow, notification_uuid)
        if row is not None and row.processing_status in {"applied", "ignored"}:
            return {"duplicate": True, "result": row.result or {}}
        if row is None:
            session.add(
                AppleNotificationEventRow(
                    notification_uuid=notification_uuid,
                    notification_type=notification_type,
                    subtype=subtype,
                    environment=environment,
                    signed_payload_sha256=signed_payload_sha256,
                    processing_status=processing_status,
                    first_seen_at=now,
                    last_seen_at=now,
                    result=result,
                    related_transaction_id=related_transaction_id,
                )
            )
        else:
            row.processing_status = processing_status
            row.last_seen_at = now
            row.result = result
            row.related_transaction_id = related_transaction_id or row.related_transaction_id
        return {"duplicate": False, "result": result}


def _handle_refund_or_revoke(
    *,
    payload: dict[str, Any],
    tenant_id: str | None,
    notification_type: str,
) -> dict[str, Any]:
    product_id = str(payload.get("productId") or "").strip()
    transaction_id = str(payload.get("transactionId") or "").strip()
    original_transaction_id = str(payload.get("originalTransactionId") or transaction_id).strip()
    tid, _ = _resolve_tenant(tenant_id=tenant_id, payload=payload, source="assn")
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


def process_notification_v2(body: dict[str, Any]) -> dict[str, Any]:
    """Verify ASSN V2 signedPayload and apply idempotently by notificationUUID."""
    if not isinstance(body, dict):
        raise AppleJwsError("notification body must be an object")
    signed = body.get("signedPayload")
    if not isinstance(signed, str) or not signed.strip():
        raise AppleJwsError("signedPayload required")
    if not iap_credentials_configured() and not body.get("_linas_test_bypass_credentials"):
        # JWS verify still possible without API key, but fail closed if ops expect keys.
        # Allow verify-only path: credentials gate is for App Store API, not JWS x5c.
        pass

    outer = decode_jws_payload(signed)
    notification_uuid = str(outer.get("notificationUUID") or "").strip()
    notification_type = str(outer.get("notificationType") or "").strip().upper()
    subtype = str(outer.get("subtype") or "").strip() or None
    data_raw = outer.get("data")
    data: dict[str, Any] = data_raw if isinstance(data_raw, dict) else {}
    environment = str(data.get("environment") or outer.get("environment") or "Unknown")
    if not notification_uuid:
        raise AppleJwsError("notificationUUID required")

    digest = sha256_hex(signed)
    with whatsapp_session() as session:
        existing = session.get(AppleNotificationEventRow, notification_uuid)
        if existing is not None and existing.processing_status in {"applied", "ignored"}:
            logger.info("apple_assn_duplicate uuid=%s type=%s", notification_uuid, notification_type)
            return {"ok": True, "duplicate": True, "notification_uuid": notification_uuid}

    signed_txn = data.get("signedTransactionInfo")
    txn_payload: dict[str, Any] | None = None
    if isinstance(signed_txn, str) and signed_txn.strip():
        txn_payload = decode_jws_payload(signed_txn)

    related_tid = str((txn_payload or {}).get("transactionId") or "") or None
    result: dict[str, Any] = {"notification_type": notification_type, "subtype": subtype}

    if notification_type == "TEST":
        result["ack"] = "test"
        _record_notification(
            notification_uuid=notification_uuid,
            notification_type=notification_type,
            subtype=subtype,
            environment=environment,
            signed_payload_sha256=digest,
            processing_status="ignored",
            result=result,
            related_transaction_id=related_tid,
        )
        return {"ok": True, "duplicate": False, "notification_uuid": notification_uuid, **result}

    if notification_type == "CONSUMPTION_REQUEST":
        result["ack"] = "consumption_request"
        # Optional send_consumption_info when caller/ops enable it later.
        _record_notification(
            notification_uuid=notification_uuid,
            notification_type=notification_type,
            subtype=subtype,
            environment=environment,
            signed_payload_sha256=digest,
            processing_status="ignored",
            result=result,
            related_transaction_id=related_tid,
        )
        return {"ok": True, "duplicate": False, "notification_uuid": notification_uuid, **result}

    if txn_payload is None:
        raise AppleJwsError("signedTransactionInfo required for this notification type")

    if notification_type in {"REFUND", "REVOKE", "REFUND_REVERSED"}:
        if notification_type == "REFUND_REVERSED":
            # Re-apply original grant path via signed transaction.
            result["reapply"] = process_signed_transaction(
                signed_transaction_jws=str(signed_txn),
                tenant_id=None,
                source=f"assn:{notification_type}",
                notification_type="SUBSCRIBED",
                decoded_payload=txn_payload,
                skip_jws_verify=True,
            )
        else:
            result["effect"] = _handle_refund_or_revoke(
                payload=txn_payload,
                tenant_id=None,
                notification_type=notification_type,
            )
    else:
        # Map renewal-status subtype for DID_CHANGE_RENEWAL_STATUS
        ntype = notification_type
        if notification_type == "DID_CHANGE_RENEWAL_STATUS" and subtype == "AUTO_RENEW_DISABLED":
            ntype = "DID_CHANGE_RENEWAL_STATUS"
        if notification_type in {"GRACE_PERIOD", "DID_FAIL_TO_RENEW", "BILLING_RETRY"}:
            ntype = "DID_FAIL_TO_RENEW"
        result["effect"] = process_signed_transaction(
            signed_transaction_jws=str(signed_txn),
            tenant_id=None,
            source=f"assn:{notification_type}",
            notification_type=ntype,
            decoded_payload=txn_payload,
            skip_jws_verify=True,
        )

    status = "ignored" if notification_type in _SKIP_NOTIFY_TYPES else "applied"
    _record_notification(
        notification_uuid=notification_uuid,
        notification_type=notification_type,
        subtype=subtype,
        environment=environment,
        signed_payload_sha256=digest,
        processing_status=status,
        result=result,
        related_transaction_id=related_tid,
    )
    return {"ok": True, "duplicate": False, "notification_uuid": notification_uuid, **result}


def reconcile_original_transaction(original_transaction_id: str) -> dict[str, Any]:
    """Pull subscription statuses from App Store API and apply any missing txns."""
    if not iap_credentials_configured():
        raise AppleIapConfigError("Apple IAP API credentials not configured")
    oid = str(original_transaction_id or "").strip()
    if not oid:
        raise ValueError("original_transaction_id required")
    data = apple_app_store_client.get_all_subscription_statuses(oid)
    applied: list[dict[str, Any]] = []
    for group in data.get("data") or []:
        if not isinstance(group, dict):
            continue
        for last in group.get("lastTransactions") or []:
            if not isinstance(last, dict):
                continue
            signed = last.get("signedTransactionInfo")
            if not isinstance(signed, str) or not signed.strip():
                continue
            try:
                applied.append(
                    process_signed_transaction(
                        signed_transaction_jws=signed,
                        tenant_id=None,
                        source="reconcile",
                    )
                )
            except (AppleJwsError, AppleIapProcessorError, PermissionError, ValueError) as exc:
                applied.append({"ok": False, "error": str(exc)})
    return {"ok": True, "original_transaction_id": oid, "results": applied}
