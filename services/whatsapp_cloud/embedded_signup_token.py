"""Fail-closed debug_token checks for WhatsApp Embedded Signup."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from services.meta_app_registry import APP_A_EXPECTED_ID
from services.whatsapp_cloud.config import WHATSAPP_REQUIRED_SCOPES
from services.whatsapp_cloud.embedded_signup_session import SignupAssetError


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def validate_embedded_signup_token(
    dbg: dict[str, Any],
    *,
    waba_id: str,
) -> list[str]:
    """Return granted scopes after proving token identity, expiry, and WABA targets."""

    payload = _as_dict(dbg)
    if payload.get("is_valid") is not True:
        raise SignupAssetError("token_invalid", "Meta debug_token reports the token is not valid")
    app_id = str(payload.get("app_id") or "").strip()
    if app_id != APP_A_EXPECTED_ID:
        raise SignupAssetError("token_wrong_app", "token does not belong to Meta App A")
    expires_at = payload.get("expires_at")
    if isinstance(expires_at, (int, float)) and int(expires_at) not in {0, None}:
        if int(expires_at) <= int(datetime.now(UTC).timestamp()):
            raise SignupAssetError("token_expired", "WhatsApp token is expired")
    scopes_raw = payload.get("scopes")
    scopes = [str(item) for item in scopes_raw] if isinstance(scopes_raw, list) else []
    granted = set(scopes)
    if not WHATSAPP_REQUIRED_SCOPES.issubset(granted):
        raise SignupAssetError(
            "scopes_missing",
            "Embedded Signup did not grant required WhatsApp permissions",
        )
    waba = str(waba_id or "").strip()
    if not waba.isdigit():
        raise SignupAssetError("asset_ids_required", "WABA id from Embedded Signup session is required")
    granular = payload.get("granular_scopes")
    if not isinstance(granular, list) or not granular:
        raise SignupAssetError("waba_not_authorized", "token granular scopes do not authorize the WABA")
    authorized: set[str] = set()
    for row in granular:
        if not isinstance(row, dict):
            continue
        scope = str(row.get("scope") or "").strip()
        if scope not in WHATSAPP_REQUIRED_SCOPES:
            continue
        targets = row.get("target_ids")
        if isinstance(targets, list):
            authorized.update(str(item).strip() for item in targets if str(item).strip().isdigit())
    if waba not in authorized:
        raise SignupAssetError("waba_not_authorized", "token granular scopes do not authorize the WABA")
    return sorted(granted)
