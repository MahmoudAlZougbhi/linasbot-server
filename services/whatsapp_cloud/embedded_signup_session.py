"""Parse and classify Meta Embedded Signup session payloads.

Official coexistence finish is only FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING.
Never treat attempt.feature_type, type=WA_EMBEDDED_SIGNUP, or a bare waba_id
as proof of that path. Never register a number.
"""

from __future__ import annotations

from typing import Any

from services.whatsapp_cloud.config import WHATSAPP_COEXISTENCE_FEATURE

PLACEHOLDER_ASSET_IDS = frozenset({"0", "123456123", "000000000000000"})
WA_EMBEDDED_SIGNUP_TYPE = "WA_EMBEDDED_SIGNUP"
COEXISTENCE_FINISH_EVENT = "FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING"
EXPECTED_SESSION_VERSION = "3"
SESSION_INFO_VERSION = "3"
EMBEDDED_SIGNUP_VERSION = "v4"

# Exact origins Meta uses for Embedded Signup postMessage. Official samples use
# a facebook.com suffix check; Linas uses equality so evilfacebook.com is denied.
META_EMBEDDED_SIGNUP_ORIGINS = frozenset(
    {
        "https://www.facebook.com",
        "https://web.facebook.com",
        "https://m.facebook.com",
        "https://facebook.com",
        "https://business.facebook.com",
        "https://staticxx.facebook.com",
        "https://l.facebook.com",
    }
)

WRONG_FLOW_EVENTS = frozenset(
    {
        "FINISH",
        "FINISH_ONLY_WABA",
        "FINISH_OBO_MIGRATION",
        "FINISH_GRANT_ONLY_API_ACCESS",
        "WA_EMBEDDED_SIGNUP",
    }
)
CANCEL_EVENTS = frozenset({"CANCEL", "CANCEL_LOGIN", "CANCELLED", "CANCELED"})
ERROR_EVENTS = frozenset({"ERROR"})
ADVANCED_ACCESS_ERROR_CODES = frozenset({"10", "200", "294"})

COEXISTENCE_PLATFORM_TYPE = "CLOUD_API"


class SignupAssetError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def origin_is_allowed(origin: str) -> bool:
    return str(origin or "").strip() in META_EMBEDDED_SIGNUP_ORIGINS


def coexistence_launch_extras() -> dict[str, Any]:
    """Launch extras: official coexistence docs plus current v4 builder version."""

    return {
        "setup": {},
        "featureType": WHATSAPP_COEXISTENCE_FEATURE,
        "sessionInfoVersion": SESSION_INFO_VERSION,
        "version": EMBEDDED_SIGNUP_VERSION,
    }


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def parse_embedded_signup_session_payload(raw: Any) -> dict[str, str]:
    """Extract session fields. Presence of waba_id is not success."""

    data = raw
    if isinstance(raw, str) and raw.strip():
        import json

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = {}
    payload = _as_dict(data)
    if str(payload.get("type") or "").strip() != WA_EMBEDDED_SIGNUP_TYPE:
        return {
            "event": "",
            "type": str(payload.get("type") or "").strip(),
            "version": "",
            "waba_id": "",
            "phone_number_id": "",
            "business_id": "",
            "error_code": "",
        }
    nested = _as_dict(payload.get("data"))
    inner = _as_dict(nested.get("data"))
    event = str(payload.get("event") or nested.get("event") or "").strip()
    msg_type = str(payload.get("type") or nested.get("type") or "").strip()
    if msg_type != WA_EMBEDDED_SIGNUP_TYPE:
        return {
            "event": "",
            "type": msg_type,
            "version": "",
            "waba_id": "",
            "phone_number_id": "",
            "business_id": "",
            "error_code": "",
        }
    version = str(payload.get("version") if payload.get("version") is not None else nested.get("version") or "").strip()
    waba = str(payload.get("waba_id") or nested.get("waba_id") or inner.get("waba_id") or "").strip()
    phone = str(
        payload.get("phone_number_id") or nested.get("phone_number_id") or inner.get("phone_number_id") or ""
    ).strip()
    business_id = str(payload.get("business_id") or nested.get("business_id") or inner.get("business_id") or "").strip()
    error_code = str(nested.get("error_code") or payload.get("error_code") or inner.get("error_code") or "").strip()
    return {
        "event": event,
        "type": msg_type,
        "version": version,
        "waba_id": waba,
        "phone_number_id": phone,
        "business_id": business_id,
        "error_code": error_code,
    }


def session_event_is_cancel(event: str) -> bool:
    return str(event or "").strip().upper() in CANCEL_EVENTS


def session_event_is_error(event: str) -> bool:
    return str(event or "").strip().upper() in ERROR_EVENTS


def session_event_is_coexistence_finish(event: str) -> bool:
    return str(event or "").strip() == COEXISTENCE_FINISH_EVENT


def session_event_is_wrong_flow(event: str) -> bool:
    return str(event or "").strip() in WRONG_FLOW_EVENTS


def is_advanced_access_error(error_code: str) -> bool:
    return str(error_code or "").strip() in ADVANCED_ACCESS_ERROR_CODES


def session_version_is_expected(version: str) -> bool:
    return str(version or "").strip() == EXPECTED_SESSION_VERSION


def assert_not_placeholder_id(value: str, *, field: str) -> str:
    raw = str(value or "").strip()
    if raw in PLACEHOLDER_ASSET_IDS:
        raise SignupAssetError("sample_phone_forbidden", f"{field} is a Meta sample placeholder")
    return raw


def phone_row_proves_coexistence(row: dict[str, Any]) -> bool:
    return row.get("is_on_biz_app") is True and str(row.get("platform_type") or "") == COEXISTENCE_PLATFORM_TYPE


def assert_coexistence_session(
    *,
    session_type: str | None,
    session_event: str | None,
    session_version: str | None,
) -> None:
    """Accept only type WA_EMBEDDED_SIGNUP + coexistence finish + session version 3."""

    if str(session_type or "").strip() != WA_EMBEDDED_SIGNUP_TYPE:
        raise SignupAssetError("coexistence_flow_required", "Embedded Signup message type is not WA_EMBEDDED_SIGNUP")
    event = str(session_event or "").strip()
    if session_event_is_cancel(event):
        raise SignupAssetError("user_cancelled", "Embedded Signup was cancelled")
    if session_event_is_error(event):
        raise SignupAssetError("meta_embedded_signup_error", "Embedded Signup reported an error")
    if not session_event_is_coexistence_finish(event):
        raise SignupAssetError(
            "coexistence_flow_required",
            "only Connect a WhatsApp Business app onboarding is accepted",
        )
    if not session_version_is_expected(str(session_version or "")):
        raise SignupAssetError("session_version_invalid", "Embedded Signup session version is not 3")


def select_proven_coexistence_phone(
    *,
    waba_id: str,
    phone_number_id: str | None,
    phones: list[dict[str, Any]],
) -> dict[str, Any]:
    """Select a phone only when Graph coexistence proof is unique and valid."""

    waba = assert_not_placeholder_id(str(waba_id or "").strip(), field="waba_id")
    if not waba.isdigit():
        raise SignupAssetError("asset_ids_required", "WABA id from Embedded Signup session is required")
    rows = [row for row in phones if isinstance(row, dict) and str(row.get("id") or "").isdigit()]
    proven = [row for row in rows if phone_row_proves_coexistence(row)]
    phone = assert_not_placeholder_id(str(phone_number_id or "").strip(), field="phone_number_id")
    if phone:
        if not phone.isdigit():
            raise SignupAssetError("asset_ids_required", "phone_number_id must be numeric")
        matched = next((row for row in rows if str(row.get("id")) == phone), None)
        if matched is None:
            raise SignupAssetError("phone_not_in_waba", "phone_number_id is not part of the shared WABA")
        if not phone_row_proves_coexistence(matched):
            raise SignupAssetError(
                "coexistence_not_proven",
                "selected phone is not proven on WhatsApp Business App Cloud API",
            )
        return matched
    if len(proven) == 1:
        return proven[0]
    if not proven:
        raise SignupAssetError("coexistence_not_proven", "no WABA phone proved WhatsApp Business App coexistence")
    raise SignupAssetError(
        "coexistence_phone_ambiguous",
        "Embedded Signup omitted phone_number_id and multiple numbers proved coexistence",
    )
