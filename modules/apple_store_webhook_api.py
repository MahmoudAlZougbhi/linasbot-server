"""Apple App Store Server Notifications V2 webhook."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException, Request

from modules.core import app
from services.apple_app_store_client import iap_credentials_configured
from services.apple_iap_processor import process_notification_v2
from services.apple_jws import AppleJwsError

logger = logging.getLogger(__name__)


async def _handle_apple_assn(request: Request) -> Any:
    if not iap_credentials_configured():
        raise HTTPException(status_code=503, detail="Apple IAP credentials not configured")
    try:
        body = await request.json()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="Invalid JSON") from exc
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Invalid payload")
    # Missing/invalid signedPayload → 400 (not 401) so auth-matrix keeps
    # webhooks classified as public (401 is reserved for session auth).
    signed = body.get("signedPayload")
    if not isinstance(signed, str) or not signed.strip():
        raise HTTPException(status_code=400, detail="signedPayload required")
    try:
        result = process_notification_v2(body)
    except AppleJwsError as exc:
        logger.warning("apple_assn_bad_signature err=%s", type(exc).__name__)
        raise HTTPException(status_code=400, detail="Invalid Apple signature") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("apple_assn_error")
        raise HTTPException(status_code=400, detail="Notification processing failed") from exc

    if result.get("duplicate"):
        logger.info(
            "apple_assn_duplicate uuid=%s type=%s",
            result.get("notification_uuid"),
            result.get("notification_type"),
        )
    return {"success": True, **result}


@app.post("/webhooks/apple/app-store")
async def apple_app_store_webhook(request: Request) -> Any:
    """ASSN V2 endpoint outside /api (middleware skips non-/api paths)."""
    return await _handle_apple_assn(request)


@app.post("/api/webhooks/apple/app-store")
async def apple_app_store_webhook_api(request: Request) -> Any:
    """ASSN V2 under /api for auth-matrix visibility + App Store Connect."""
    return await _handle_apple_assn(request)


@app.post("/api/entitlements/apple/notifications")
async def apple_notifications_alias(request: Request) -> Any:
    """Alias kept for App Store Connect URL compatibility."""
    return await _handle_apple_assn(request)
