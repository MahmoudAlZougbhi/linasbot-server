"""Apple / Google store notification endpoints + IAP readiness.

Apple ASSN V2 live handling lives in ``modules.apple_store_webhook_api``
(``POST /webhooks/apple/app-store`` and alias
``POST /api/entitlements/apple/notifications``).
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from modules.api_security import require_platform_owner, require_session
from modules.core import app
from services.store_iap_service import (
    apply_normalized_notification,
    external_store_checklist,
    iap_config_status,
    normalize_apple_status,
    normalize_google_status,
    verify_google_notification_payload,
)


class ManualStoreEvent(BaseModel):
    """Platform-owner sandbox/manual injection after verified external purchase."""

    tenant_id: str
    source: str = Field(pattern="^(apple|google)$")
    product_id: str
    status_hint: str
    original_transaction_id: str = Field(min_length=4)
    event_id: str = Field(min_length=8)


@app.get("/api/entitlements/iap/status")
async def iap_status(request: Request) -> Any:
    require_session(request)
    status = iap_config_status()
    return {"success": True, "iap": status, "checklist": external_store_checklist()}


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


@app.post("/api/entitlements/iap/manual-event")
async def iap_manual_event(body: ManualStoreEvent, request: Request) -> Any:
    """Owner-only path for verified sandbox events until store webhooks are live."""
    require_platform_owner(request)
    if body.source == "apple":
        status = normalize_apple_status(body.status_hint)
    else:
        status = normalize_google_status(body.status_hint)
    result = apply_normalized_notification(
        tenant_id=body.tenant_id,
        source=body.source,  # type: ignore[arg-type]
        product_id=body.product_id,
        status=status,
        original_transaction_id=body.original_transaction_id,
        event_id=body.event_id,
    )
    return {"success": True, **result}
