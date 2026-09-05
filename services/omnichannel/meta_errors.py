"""Typed Meta Graph errors that preserve Retry-After and usage headers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from services.omnichannel.headers import parse_meta_usage, parse_retry_after_seconds

OutboundFinishStatus = Literal["accepted", "definitive_failure", "needs_owner_action"]


class MetaProviderError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        http_status: int,
        error_code: int | str = "unknown",
        error_subcode: int | str = "unknown",
        headers: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.http_status = int(http_status)
        self.error_code = error_code
        self.error_subcode = error_subcode
        self.retry_after_seconds = parse_retry_after_seconds(headers)
        self.usage = parse_meta_usage(headers)

    @property
    def retryable(self) -> bool:
        from services.omnichannel.classify import classify_http_delivery

        decision = classify_http_delivery(
            http_status=self.http_status,
            provider_code=self.error_code,
            provider_subcode=self.error_subcode,
        )
        return bool(decision.retryable)


def raise_from_meta_response(response: Any) -> None:
    error_code: int | str = "unknown"
    error_subcode: int | str = "unknown"
    error_message = ""
    try:
        error_payload = response.json()
        error = error_payload.get("error") if isinstance(error_payload, dict) else None
        if isinstance(error, dict):
            raw_code = error.get("code")
            raw_subcode = error.get("error_subcode")
            if isinstance(raw_code, int):
                error_code = raw_code
            elif raw_code is not None and str(raw_code).strip().isdigit():
                error_code = int(str(raw_code).strip())
            if isinstance(raw_subcode, int):
                error_subcode = raw_subcode
            error_message = str(error.get("message") or "").strip()[:180]
    except (TypeError, ValueError):
        pass
    detail = f" {error_message}" if error_message else ""
    raise MetaProviderError(
        f"Meta Send API returned HTTP {response.status_code} code={error_code} subcode={error_subcode}{detail}",
        http_status=int(response.status_code),
        error_code=error_code,
        error_subcode=error_subcode,
        headers=getattr(response, "headers", None),
    )


def finish_status_for_send_exception(exc: BaseException) -> tuple[OutboundFinishStatus, str]:
    """Map a provider exception to outbound-attempt status. 429/613 retry; unknown stays owner-action."""

    if isinstance(exc, MetaProviderError) and exc.retryable:
        return "definitive_failure", "provider_throttled_or_unavailable"
    from services.omnichannel.classify import classify_http_delivery

    decision = classify_http_delivery(
        http_status=getattr(exc, "http_status", None),
        provider_code=getattr(exc, "error_code", None),
        error_text=str(exc),
    )
    if decision.retryable:
        return "definitive_failure", decision.reason or "provider_throttled_or_unavailable"
    return "needs_owner_action", "provider_call_ambiguous"
