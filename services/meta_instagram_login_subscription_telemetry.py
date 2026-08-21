"""Secret-safe Graph telemetry for Instagram Login subscribed_apps calls."""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

_runtime_logger = logging.getLogger("uvicorn.error")
_SAFE_ERROR_TYPE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_ALLOWED_STAGES = frozenset({"subscribe", "verify"})
_EMPTY = "-"


def _safe_int_field(value: object) -> str:
    if isinstance(value, bool) or not isinstance(value, int):
        return ""
    if abs(value) > 1_000_000_000:
        return ""
    return str(value)


def _safe_error_type(value: object) -> str:
    if isinstance(value, str) and _SAFE_ERROR_TYPE.fullmatch(value):
        return value
    return ""


def _safe_request_id(value: object) -> str:
    if isinstance(value, str) and _SAFE_REQUEST_ID.fullmatch(value.strip()):
        return value.strip()
    return ""


def _safe_is_transient(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return ""


def _error_object(payload: object) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    error = payload.get("error")
    return error if isinstance(error, dict) else None


def extract_instagram_subscribed_apps_telemetry(response: httpx.Response) -> dict[str, str]:
    """Return Graph diagnostics that never include tokens, bodies, or account IDs."""

    payload: object = None
    try:
        payload = response.json()
    except ValueError:
        payload = None
    error = _error_object(payload)
    return {
        "http_status": str(response.status_code),
        "error_type": _safe_error_type(error.get("type") if error else None),
        "error_code": _safe_int_field(error.get("code") if error else None),
        "error_subcode": _safe_int_field(error.get("error_subcode") if error else None),
        "is_transient": _safe_is_transient(error.get("is_transient") if error else None),
        "x_fb_request_id": _safe_request_id(response.headers.get("x-fb-request-id")),
    }


def _should_emit(response: httpx.Response, *, require_success_flag: bool) -> bool:
    if response.status_code < 200 or response.status_code >= 300:
        return True
    payload: object
    try:
        payload = response.json()
    except ValueError:
        return True
    if _error_object(payload) is not None:
        return True
    if require_success_flag:
        return not (isinstance(payload, dict) and payload.get("success") is True)
    return False


def log_instagram_subscribed_apps_telemetry(
    response: httpx.Response,
    *,
    stage: str,
    require_success_flag: bool = False,
) -> None:
    """Emit subscribe/verify diagnostics without secrets or raw Graph text."""

    try:
        if not _should_emit(response, require_success_flag=require_success_flag):
            return
        safe_stage = stage if stage in _ALLOWED_STAGES else "unknown"
        fields = extract_instagram_subscribed_apps_telemetry(response)
        _runtime_logger.warning(
            "[instagram-login] subscribed_apps stage=%s http_status=%s error_type=%s "
            "error_code=%s error_subcode=%s is_transient=%s x_fb_request_id=%s",
            safe_stage,
            fields["http_status"] or _EMPTY,
            fields["error_type"] or _EMPTY,
            fields["error_code"] or _EMPTY,
            fields["error_subcode"] or _EMPTY,
            fields["is_transient"] or _EMPTY,
            fields["x_fb_request_id"] or _EMPTY,
        )
    except Exception:
        return
