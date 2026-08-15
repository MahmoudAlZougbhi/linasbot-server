"""Core Apple IAP authority: signed transactions + ASSN V2 + reconcile."""

from __future__ import annotations

import logging
from typing import Any

from services import apple_transaction_ledger as txn_ledger
from services.apple_app_store_client import (
    AppleIapConfigError,
    apple_app_store_client,
    iap_credentials_configured,
)
from services.apple_assn_handlers import (
    handle_apply_txn,
    handle_consumable_only,
    handle_consumption_request,
    handle_metadata_only,
    handle_refund_or_revoke,
    handle_refund_reversed,
    resolve_tenant,
)
from services.apple_assn_types import classify_assn_action
from services.apple_iap_effects import (
    apply_subscription_effect,
    bump_entitlement_period_from_expires,
    classify_product,
    grant_consumable_credits,
    subscription_status_from_payload,
)
from services.apple_jws import AppleJwsError, decode_jws_payload, sha256_hex
from services.apple_notification_claim import claim_notification, finalize_notification
from services.apple_renewal_info import decode_and_apply_renewal_info

logger = logging.getLogger(__name__)


class AppleIapProcessorError(RuntimeError):
    """Processing failure (config, tenant, or payload)."""


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

    try:
        tid_resolved, token_user = resolve_tenant(tenant_id=tenant_id, payload=payload, source=source)
    except ValueError as exc:
        raise AppleIapProcessorError(str(exc)) from exc
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
            notification_type=notification_type,
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


def process_notification_v2(body: dict[str, Any]) -> dict[str, Any]:
    """Verify ASSN V2 signedPayload and apply idempotently by notificationUUID.

    Claim-before-effect: insert ``processing`` immediately after UUID extract.
    On exception after claim, finalize as ``failed`` (failed may be re-driven).
    """
    if not isinstance(body, dict):
        raise AppleJwsError("notification body must be an object")
    signed = body.get("signedPayload")
    if not isinstance(signed, str) or not signed.strip():
        raise AppleJwsError("signedPayload required")
    if not iap_credentials_configured() and not body.get("_linas_test_bypass_credentials"):
        # JWS verify still possible without API key; API key is for App Store Server API.
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
    # Claim IMMEDIATELY after UUID extract — before any financial effect.
    claim = claim_notification(
        notification_uuid=notification_uuid,
        notification_type=notification_type,
        subtype=subtype,
        environment=environment,
        signed_payload_sha256=digest,
    )
    if claim.get("duplicate"):
        logger.info("apple_assn_duplicate uuid=%s type=%s", notification_uuid, notification_type)
        return {
            "ok": True,
            "duplicate": True,
            "notification_uuid": notification_uuid,
            "processing_status": claim.get("processing_status"),
            **(claim.get("result") or {}),
        }

    result: dict[str, Any] = {"notification_type": notification_type, "subtype": subtype}
    related_tid: str | None = None
    final_status = "applied"

    try:
        signed_txn = data.get("signedTransactionInfo")
        txn_payload: dict[str, Any] | None = None
        if isinstance(signed_txn, str) and signed_txn.strip():
            txn_payload = decode_jws_payload(signed_txn)
        related_tid = str((txn_payload or {}).get("transactionId") or "") or None

        signed_renewal = data.get("signedRenewalInfo")
        renewal_result: dict[str, Any] | None = None
        if isinstance(signed_renewal, str) and signed_renewal.strip() and txn_payload is not None:
            renewal_result = decode_and_apply_renewal_info(
                signed_renewal,
                tenant_id=None,
                notification_type=notification_type,
                subtype=subtype,
                txn_payload=txn_payload,
            )
            result["renewal"] = renewal_result

        classified = classify_assn_action(notification_type, subtype)
        result["classification"] = {
            "action": classified["action"],
            "status": classified.get("status"),
            "effect_kind": classified.get("effect_kind"),
        }
        action = classified["action"]

        if action == "ignore":
            reason = classified.get("reason") or classified.get("effect_kind") or "ignored"
            result["ack"] = reason
            final_status = "ignored"
            if classified.get("effect_kind") == "failed_unknown_type":
                result["reason"] = "failed_unknown_type"
                logger.warning(
                    "apple_assn_unknown_type uuid=%s type=%s — no financial effect",
                    notification_uuid,
                    notification_type,
                )
        elif action == "consumption":
            result.update(handle_consumption_request(payload=txn_payload, related_transaction_id=related_tid))
        elif action == "refund_reversed":
            if txn_payload is None:
                raise AppleJwsError("signedTransactionInfo required for REFUND_REVERSED")
            result["effect"] = handle_refund_reversed(payload=txn_payload, tenant_id=None)
        elif action == "refund":
            if txn_payload is None:
                raise AppleJwsError("signedTransactionInfo required for REFUND/REVOKE")
            result["effect"] = handle_refund_or_revoke(
                payload=txn_payload,
                tenant_id=None,
                notification_type=notification_type,
            )
        elif action == "metadata":
            result["effect"] = handle_metadata_only(
                notification_type=notification_type,
                subtype=subtype,
                renewal=renewal_result,
            )
            # Metadata-only: no status→active. Renewal info may still have applied grace/cancel.
        elif action == "apply_txn":
            if txn_payload is None or not isinstance(signed_txn, str):
                raise AppleJwsError("signedTransactionInfo required for this notification type")
            if classified.get("effect_kind") == "consumable_only":
                result["effect"] = handle_consumable_only(
                    process_signed_transaction_fn=process_signed_transaction,
                    signed_transaction_jws=str(signed_txn),
                    txn_payload=txn_payload,
                    notification_type=notification_type,
                )
                if result["effect"].get("skipped"):
                    final_status = "ignored"
            else:
                result["effect"] = handle_apply_txn(
                    process_signed_transaction_fn=process_signed_transaction,
                    signed_transaction_jws=str(signed_txn),
                    txn_payload=txn_payload,
                    notification_type=notification_type,
                    status=classified.get("status"),
                )
        elif action == "error":
            raise AppleIapProcessorError(classified.get("reason") or f"unhandled ASSN action for {notification_type}")
        else:
            raise AppleIapProcessorError(f"unknown ASSN action: {action}")

        finalize_notification(
            notification_uuid=notification_uuid,
            processing_status=final_status,
            result=result,
            related_transaction_id=related_tid,
            notification_type=notification_type,
            subtype=subtype,
        )
        return {
            "ok": True,
            "duplicate": False,
            "notification_uuid": notification_uuid,
            **result,
        }
    except Exception as exc:
        # Crash recovery: failed may be re-driven via claim_notification.
        logger.exception(
            "apple_assn_failed uuid=%s type=%s err=%s",
            notification_uuid,
            notification_type,
            exc,
        )
        fail_result = {
            **result,
            "error": str(exc)[:500],
            "failed": True,
        }
        try:
            finalize_notification(
                notification_uuid=notification_uuid,
                processing_status="failed",
                result=fail_result,
                related_transaction_id=related_tid,
                notification_type=notification_type,
                subtype=subtype,
            )
        except Exception as fin_exc:  # noqa: BLE001
            logger.error(
                "apple_assn_finalize_failed uuid=%s err=%s",
                notification_uuid,
                fin_exc,
            )
        raise


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
