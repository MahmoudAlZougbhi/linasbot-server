"""Classify provider delivery outcomes. Never treat 429/613 as owner-action."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from services.omnichannel.backoff import delay_for_provider
from services.omnichannel.contract import DeliveryDecision
from services.omnichannel.headers import parse_tiktok_request_id

_TRANSIENT_HTTP = frozenset({408, 425, 429, 500, 502, 503, 504})
_PERMISSION_HTTP = frozenset({401, 403})
_META_THROTTLE_CODES = frozenset({"4", "17", "32", "613", "80007", "613000"})
_PERM_MARKERS = (
    "permission",
    "not authorized",
    "oauth",
    "disconnected",
    "permanently closed",
    "#200",
    "#10",
)
_STATUS_RE = re.compile(r"(?:^|_)(?:http|graph_http|status)[_:]?(4\d\d|5\d\d)(?:_|$)", re.I)


def _int_status(*values: Any) -> int | None:
    for value in values:
        if isinstance(value, int) and 100 <= value <= 599:
            return value
        text = str(value or "").strip()
        if text.isdigit():
            parsed = int(text)
            if 100 <= parsed <= 599:
                return parsed
        match = _STATUS_RE.search(str(value or ""))
        if match:
            return int(match.group(1))
    return None


def _code(*values: Any) -> str:
    for value in values:
        if value is None or value == "":
            continue
        return str(value).strip()
    return ""


def classify_http_delivery(
    *,
    http_status: int | None = None,
    provider_code: str | int | None = None,
    provider_subcode: str | int | None = None,
    error_text: str = "",
    headers: Mapping[str, Any] | None = None,
    body: Mapping[str, Any] | None = None,
    submitted: bool = False,
    local_update_failed: bool = False,
    attempt: int = 0,
    connection_reset_before_submit: bool = False,
    malformed_response: bool = False,
    token_expired: bool = False,
) -> DeliveryDecision:
    status = _int_status(http_status)
    code = _code(provider_code)
    subcode = _code(provider_subcode)
    low = (error_text or "").strip().lower()
    request_id = parse_tiktok_request_id(headers, body if isinstance(body, dict) else None)
    delay = delay_for_provider(attempt=attempt, headers=headers)

    if local_update_failed and submitted:
        return DeliveryDecision(
            kind="ambiguous",
            retry_after_seconds=delay,
            http_status=status,
            provider_code=code,
            provider_subcode=subcode,
            provider_request_id=request_id,
            reason="accepted_local_state_update_failed",
            retryable=False,
        )
    if submitted and (status is None or status >= 500 or status in {408, 504}):
        return DeliveryDecision(
            kind="ambiguous",
            retry_after_seconds=delay,
            http_status=status,
            provider_code=code,
            provider_subcode=subcode,
            provider_request_id=request_id,
            reason="timeout_or_5xx_after_submit",
            retryable=False,
        )
    if connection_reset_before_submit:
        return DeliveryDecision(
            kind="transient",
            retry_after_seconds=delay,
            reason="connection_reset_before_submit",
            retryable=True,
        )
    if malformed_response:
        return DeliveryDecision(
            kind="ambiguous" if submitted else "transient",
            retry_after_seconds=delay,
            http_status=status,
            reason="malformed_or_non_json_response",
            retryable=not submitted,
        )
    if token_expired:
        return DeliveryDecision(
            kind="permission_blocked",
            http_status=status or 401,
            provider_code=code or "token_expired",
            reason="expired_token",
            retryable=False,
        )
    if status in _TRANSIENT_HTTP or code in _META_THROTTLE_CODES:
        return DeliveryDecision(
            kind="transient",
            retry_after_seconds=delay,
            http_status=status,
            provider_code=code,
            provider_subcode=subcode,
            provider_request_id=request_id,
            reason="provider_throttled_or_unavailable",
            retryable=True,
        )
    if status in _PERMISSION_HTTP:
        return DeliveryDecision(
            kind="permission_blocked",
            http_status=status,
            provider_code=code,
            provider_subcode=subcode,
            reason="permission_or_auth",
            retryable=False,
        )
    if status == 400 or any(marker in low for marker in _PERM_MARKERS):
        return DeliveryDecision(
            kind="permanent",
            http_status=status,
            provider_code=code,
            provider_subcode=subcode,
            reason="definitive_client_rejection",
            retryable=False,
        )
    if status is not None and 400 <= status < 500:
        return DeliveryDecision(
            kind="permanent",
            http_status=status,
            provider_code=code,
            provider_subcode=subcode,
            reason="client_error",
            retryable=False,
        )
    if status is not None and 200 <= status < 300:
        return DeliveryDecision(
            kind="success",
            http_status=status,
            provider_request_id=request_id,
            reason="provider_accepted",
            retryable=False,
        )
    return DeliveryDecision(
        kind="ambiguous",
        retry_after_seconds=delay,
        http_status=status,
        provider_code=code,
        reason="unclassified_provider_result",
        retryable=False,
    )


def is_transient_http_status(status: int | None) -> bool:
    return status in _TRANSIENT_HTTP


def returned_rejection_is_definitive(result: Any) -> bool:
    """True only when the provider proved it did not accept the send."""

    if not isinstance(result, dict):
        return False
    status = _int_status(
        result.get("status_code"),
        result.get("http_status"),
        result.get("error"),
        result.get("error_message"),
        result.get("reason"),
    )
    code = _code(result.get("code"), result.get("error_code"), result.get("provider_code"))
    if status in _TRANSIENT_HTTP or code in _META_THROTTLE_CODES:
        return False
    if status is not None and 400 <= status < 500:
        return True
    return False
