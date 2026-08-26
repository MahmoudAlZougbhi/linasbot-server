"""Helpers for Meta App Review WhatsApp bind (LOC split)."""

from __future__ import annotations

import hashlib
import os
import uuid
from typing import Any

from services.meta_app_registry import APP_A_EXPECTED_ID, APP_A_KEY, get_meta_app_configs
from services.whatsapp_cloud.config import WHATSAPP_REQUIRED_SCOPES
from services.whatsapp_cloud.graph_client import (
    WhatsAppGraphError,
    debug_token,
    fetch_waba_phone_numbers,
)

# Constants mirrored from app_review_bind for helper use.
APP_REVIEW_SOURCE = "meta_app_review_test"
APP_REVIEW_TENANT_ID = "linas"
TOKEN_ENV = "META_WHATSAPP_APP_REVIEW_BIND_TOKEN"
ALLOWED_WABA_ENV = "META_WHATSAPP_APP_REVIEW_ALLOWED_WABA_IDS"


class AppReviewBindError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _mask_id(value: str) -> str:
    raw = str(value or "").strip()
    if len(raw) <= 6:
        return "***"
    return f"{raw[:3]}…{raw[-3:]}"


def _require_token(access_token: str | None) -> str:
    token = (access_token or os.getenv(TOKEN_ENV) or "").strip()
    if not token:
        raise AppReviewBindError(
            "token_required",
            f"Provide a fresh WhatsApp token via argument or env {TOKEN_ENV} (never commit/print it)",
        )
    if len(token) < 20:
        raise AppReviewBindError("token_invalid", "access token is too short to be valid")
    return token


def _allowed_waba_ids() -> frozenset[str] | None:
    raw = (os.getenv(ALLOWED_WABA_ENV) or "").strip()
    if not raw:
        return None
    values = {part.strip() for part in raw.split(",") if part.strip().isdigit()}
    return frozenset(values) if values else None


def _assert_tenant(tenant_id: str) -> str:
    tid = str(tenant_id or "").strip()
    if tid != APP_REVIEW_TENANT_ID:
        raise AppReviewBindError(
            "tenant_forbidden",
            f"temporary bind is only allowed for tenant {APP_REVIEW_TENANT_ID}",
        )
    return tid


def _assert_numeric_ids(*, waba_id: str, phone_number_id: str) -> tuple[str, str]:
    waba = str(waba_id or "").strip()
    phone = str(phone_number_id or "").strip()
    if not waba.isdigit() or not phone.isdigit():
        raise AppReviewBindError("asset_ids_invalid", "waba_id and phone_number_id must be numeric")
    if phone == "123456123":
        raise AppReviewBindError(
            "sample_phone_forbidden",
            "Meta sample phone_number_id 123456123 is not a real asset",
        )
    allowed = _allowed_waba_ids()
    if allowed is not None and waba not in allowed:
        raise AppReviewBindError("waba_not_allowlisted", f"WABA is not in {ALLOWED_WABA_ENV}")
    return waba, phone


def _correlation_id(idempotency_key: str | None) -> str:
    raw = str(idempotency_key or "").strip()
    if raw:
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
    return uuid.uuid4().hex


def _is_app_review_connection(conn: Any) -> bool:
    source = str(getattr(conn, "connection_source", "") or "")
    if source == APP_REVIEW_SOURCE:
        return True
    return (getattr(conn, "health_detail", None) or "") == APP_REVIEW_SOURCE


async def _validate_meta_assets(
    *,
    access_token: str,
    waba_id: str,
    phone_number_id: str,
) -> tuple[dict[str, Any], list[str], dict[str, Any]]:
    app = get_meta_app_configs()[APP_A_KEY]
    if not app.enabled or app.app_id != APP_A_EXPECTED_ID:
        raise AppReviewBindError("app_a_unavailable", "Meta App A is not configured")
    try:
        dbg = await debug_token(input_token=access_token, app_id=app.app_id, app_secret=app.app_secret)
    except WhatsAppGraphError as exc:
        raise AppReviewBindError("token_debug_failed", exc.message) from exc
    if not dbg.get("is_valid", True):
        raise AppReviewBindError("token_invalid", "Meta debug_token reports token is not valid")
    token_app_id = str(dbg.get("app_id") or "").strip()
    if token_app_id != app.app_id:
        raise AppReviewBindError(
            "token_app_mismatch",
            "Meta token belongs to a different app",
        )
    scopes_raw = dbg.get("scopes") if isinstance(dbg, dict) else None
    scopes = [str(s) for s in scopes_raw] if isinstance(scopes_raw, list) else []
    granted = set(scopes)
    if not WHATSAPP_REQUIRED_SCOPES.issubset(granted):
        raise AppReviewBindError(
            "scopes_missing",
            "token is missing whatsapp_business_management and/or whatsapp_business_messaging",
        )
    try:
        phones = await fetch_waba_phone_numbers(access_token=access_token, waba_id=waba_id)
    except WhatsAppGraphError as exc:
        raise AppReviewBindError("waba_phones_failed", exc.message) from exc
    matched = next((p for p in phones if str(p.get("id")) == phone_number_id), None)
    if matched is None:
        raise AppReviewBindError("phone_not_in_waba", "phone_number_id is not part of the supplied WABA")
    return matched, sorted(granted & (WHATSAPP_REQUIRED_SCOPES | {"business_management"})), dbg
