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


@app.post("/api/entitlements/google/notifications")
async def google_notifications(request: Request) -> Any:
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Invalid payload")
    try:
        parsed = verify_google_notification_payload(body)
    except PermissionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    result = apply_normalized_notification(
        tenant_id=str(parsed["tenant_id"]),
        source="google",
        product_id=str(parsed["product_id"]),
        status=normalize_google_status(str(parsed.get("subscription_state") or "")),
        original_transaction_id=str(parsed["original_transaction_id"]),
        event_id=str(parsed["event_id"]),
    )
    return {"success": True, **result}
