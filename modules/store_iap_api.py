"""Google Play Real-time Developer Notifications.

Apple ASSN V2 live handling lives in ``modules.apple_store_webhook_api``
(``POST /webhooks/apple/app-store`` and alias
``POST /api/entitlements/apple/notifications``).
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request

from modules.core import app
from services.store_iap_service import (
    apply_normalized_notification,
    normalize_google_status,
    verify_google_notification_payload,
)


def apply_google_notification_effect(parsed: dict[str, Any]) -> dict[str, Any]:
    from services.membership.iap_message_grant import (
        maybe_grant_purchased_from_verified_txn,
        maybe_revoke_purchased_from_verified_txn,
    )

    tenant_id = str(parsed["tenant_id"])
    product_id = str(parsed["product_id"])
    txn_id = str(parsed["original_transaction_id"])
    state = str(parsed.get("subscription_state") or "").upper()
    if "REVOKED" in state or "REFUND" in state:
        message_key = "message_revoke"
        message_effect = maybe_revoke_purchased_from_verified_txn(
            tenant_id=tenant_id,
            transaction_id=txn_id,
        )
    elif "ACTIVE" in state:
        message_key = "message_grant"
        message_effect = maybe_grant_purchased_from_verified_txn(
            tenant_id=tenant_id,
            product_id=product_id,
            transaction_id=txn_id,
        )
    else:
        message_key = "message_grant"
        message_effect = {"granted": False, "reason": "not_active_purchase"}
    try:
        result = apply_normalized_notification(
            tenant_id=tenant_id,
            source="google",
            product_id=product_id,
            status=normalize_google_status(str(parsed.get("subscription_state") or "")),
            original_transaction_id=txn_id,
            event_id=str(parsed["event_id"]),
        )
    except ValueError:
        if message_effect.get("granted") or message_effect.get("revoked"):
            return {message_key: message_effect}
        raise
    result[message_key] = message_effect
    return result


@app.post("/api/entitlements/google/notifications")
async def google_notifications(request: Request) -> Any:
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Invalid payload")
    try:
        parsed = verify_google_notification_payload(body)
    except PermissionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    try:
        result = apply_google_notification_effect(parsed)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, **result}
