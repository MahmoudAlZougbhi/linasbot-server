"""TikTok enhanced post-context capability keys, reason codes, and user status."""

from __future__ import annotations

from typing import Any

TOKEN_KIND_ACCOUNT = "account_holder"
TOKEN_KIND_ADVERTISER = "advertiser"

CAPABILITY_KEYS: tuple[str, ...] = (
    "account_basic",
    "video_list",
    "comments_read",
    "comments_manage",
    "identity_query",
    "business_center_asset",
    "identity_video_query",
    "official_video_media_available",
    "caption_available",
    "thumbnail_available",
    "full_video_context_available",
)

REASON_CODES: tuple[str, ...] = (
    "permission_not_approved",
    "token_type_mismatch",
    "missing_business_center_binding",
    "missing_advertiser_binding",
    "identity_not_authorized",
    "unsupported_endpoint",
    "media_url_not_available",
    "expired_media_url",
    "rate_limited",
    "api_error",
    "reauthorization_required",
    "waiting_for_permission",
    "authorization_required",
)

USER_STATUSES: tuple[str, ...] = (
    "waiting_for_permission",
    "authorization_required",
    "identity_authorization_required",
    "reauthorization_required",
    "active",
    "limited",
    "error",
)

ENHANCED_LABEL = "Enhanced Video Context"
CONTEXT_LEVELS = ("comment_only", "caption_only", "caption_thumbnail", "full_video")

ADVERTISER_ONLY_PREFIXES: tuple[str, ...] = (
    "/identity/",
    "/bc/",
    "/oauth2/advertiser/get/",
)

TERMINAL_COOLDOWN_REASONS = frozenset(
    {
        "permission_not_approved",
        "unsupported_endpoint",
        "token_type_mismatch",
        "waiting_for_permission",
    }
)

PERMISSION_TIKTOK_CODES = frozenset({40001, 40002, 40131, 40300})
RATE_LIMIT_TIKTOK_CODES = frozenset({40100})
TOKEN_BAD_TIKTOK_CODES = frozenset({40104, 40105})


def empty_capabilities() -> dict[str, bool]:
    return {key: False for key in CAPABILITY_KEYS}


def is_advertiser_only_path(path: str) -> bool:
    cleaned = str(path or "").strip()
    return any(cleaned.startswith(prefix) for prefix in ADVERTISER_ONLY_PREFIXES)


def classify_tiktok_error(*, tiktok_code: int | None, message: str = "") -> str:
    text = str(message or "").lower()
    if tiktok_code in RATE_LIMIT_TIKTOK_CODES:
        return "rate_limited"
    if tiktok_code in TOKEN_BAD_TIKTOK_CODES:
        if "incorrect" in text or "revoked" in text or tiktok_code == 40105:
            return "token_type_mismatch"
        return "reauthorization_required"
    if tiktok_code in PERMISSION_TIKTOK_CODES:
        if "not one of the allowed" in text or "unsupported" in text:
            return "unsupported_endpoint"
        return "permission_not_approved"
    if "not approved" in text or "no permission" in text or "access denied" in text:
        return "permission_not_approved"
    if "not one of the allowed" in text or "unsupported" in text:
        return "unsupported_endpoint"
    return "api_error"


def user_status_for(*, reason: str, identity_id: str = "", media_available: bool = False) -> str:
    if reason in {"waiting_for_permission", "permission_not_approved"}:
        return "waiting_for_permission"
    if reason == "authorization_required":
        return "authorization_required"
    if reason == "reauthorization_required":
        return "reauthorization_required"
    if reason in {"identity_not_authorized", "missing_advertiser_binding", "missing_business_center_binding"}:
        return "identity_authorization_required"
    if reason == "token_type_mismatch":
        return "error"
    if reason in {"api_error", "rate_limited", "unsupported_endpoint"}:
        return "error" if reason == "api_error" else "limited"
    if reason in {"", "ok"} and identity_id:
        return "active"
    if identity_id and media_available:
        return "active"
    if identity_id:
        return "limited"
    if reason == "media_url_not_available":
        return "limited"
    return "authorization_required"


def user_message_for(status: str) -> str:
    if status == "waiting_for_permission":
        return "Waiting for TikTok approval"
    if status == "authorization_required":
        return "Authorization required"
    if status == "identity_authorization_required":
        return "Identity authorization required"
    if status == "reauthorization_required":
        return "Authorization required"
    if status == "active":
        return "Active"
    if status == "limited":
        return "Limited by TikTok"
    if status == "error":
        return "Error"
    return "Authorization required"


def default_binding_payload() -> dict[str, Any]:
    return {
        "status": "authorization_required",
        "reason_code": "authorization_required",
        "capabilities": empty_capabilities(),
        "advertiser_id": "",
        "bc_id": "",
        "identity_id": "",
        "identity_type": "",
        "identity_authorized_bc_id": "",
    }
