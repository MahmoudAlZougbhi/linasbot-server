"""Parse Meta Embedded Signup session payloads and resolve WABA phones.

Official coexistence FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING often includes
only waba_id. Never treat Meta sample IDs as real assets. Never register.
"""

from __future__ import annotations

from typing import Any

from services.whatsapp_cloud.config import WHATSAPP_COEXISTENCE_FEATURE

PLACEHOLDER_ASSET_IDS = frozenset({"0", "123456123", "000000000000000"})
COEXISTENCE_FINISH_EVENTS = frozenset(
    {
        "FINISH",
        "FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING",
        "WA_EMBEDDED_SIGNUP",
    }
)
CANCEL_EVENTS = frozenset({"CANCEL", "CANCEL_LOGIN", "CANCELLED", "CANCELED"})


class SignupAssetError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def parse_embedded_signup_session_payload(raw: Any) -> dict[str, str]:
    """Extract waba_id, phone_number_id, and event from a Meta postMessage payload."""

    data = raw
    if isinstance(raw, str) and raw.strip():
        import json

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = {}
    payload = _as_dict(data)
    nested = _as_dict(payload.get("data"))
    inner = _as_dict(nested.get("data"))
    event = str(payload.get("event") or nested.get("event") or payload.get("type") or "").strip()
    waba = str(payload.get("waba_id") or nested.get("waba_id") or inner.get("waba_id") or "").strip()
    phone = str(
        payload.get("phone_number_id") or nested.get("phone_number_id") or inner.get("phone_number_id") or ""
    ).strip()
    return {"event": event, "waba_id": waba, "phone_number_id": phone}


def session_event_is_cancel(event: str) -> bool:
    return str(event or "").strip().upper() in CANCEL_EVENTS


def session_event_is_coexistence_finish(event: str) -> bool:
    return str(event or "").strip() in COEXISTENCE_FINISH_EVENTS


def assert_not_placeholder_id(value: str, *, field: str) -> str:
    raw = str(value or "").strip()
    if raw in PLACEHOLDER_ASSET_IDS:
        raise SignupAssetError("sample_phone_forbidden", f"{field} is a Meta sample placeholder")
    return raw


def resolve_signup_phone(
    *,
    waba_id: str,
    phone_number_id: str | None,
    phones: list[dict[str, Any]],
) -> dict[str, Any]:
    """Match session phone_number_id, or use the sole WABA number when Meta omitted it."""

    waba = assert_not_placeholder_id(str(waba_id or "").strip(), field="waba_id")
    if not waba.isdigit():
        raise SignupAssetError("asset_ids_required", "WABA id from Embedded Signup session is required")
    phone = assert_not_placeholder_id(str(phone_number_id or "").strip(), field="phone_number_id")
    rows = [row for row in phones if isinstance(row, dict) and str(row.get("id") or "").isdigit()]
    if phone:
        if not phone.isdigit():
            raise SignupAssetError("asset_ids_required", "phone_number_id must be numeric")
        matched = next((row for row in rows if str(row.get("id")) == phone), None)
        if matched is None:
            raise SignupAssetError("phone_not_in_waba", "phone_number_id is not part of the shared WABA")
        return matched
    if len(rows) == 1:
        return rows[0]
    if not rows:
        raise SignupAssetError("waba_has_no_phones", "shared WABA has no phone numbers")
    raise SignupAssetError(
        "phone_ambiguous",
        "Embedded Signup omitted phone_number_id and the WABA has multiple numbers",
    )


def coexistence_launch_extras() -> dict[str, Any]:
    """Exact extras required by current Meta coexistence documentation."""

    return {
        "setup": {},
        "featureType": WHATSAPP_COEXISTENCE_FEATURE,
        "sessionInfoVersion": "3",
    }
