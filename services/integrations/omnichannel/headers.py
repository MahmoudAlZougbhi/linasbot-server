"""Parse provider rate-limit and identity headers without logging secrets."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

_RETRY_AFTER = "retry-after"
_APP_USAGE = "x-app-usage"
_PAGE_USAGE = "x-page-usage"
_BUC_USAGE = "x-business-use-case-usage"
_OPENAI_REMAINING_REQUESTS = "x-ratelimit-remaining-requests"
_OPENAI_REMAINING_TOKENS = "x-ratelimit-remaining-tokens"
_OPENAI_RESET_REQUESTS = "x-ratelimit-reset-requests"
_OPENAI_RESET_TOKENS = "x-ratelimit-reset-tokens"
_TIKTOK_REQUEST_ID = "x-tt-logid"


def _header(headers: Mapping[str, Any] | None, name: str) -> str:
    if not headers:
        return ""
    lowered = {str(key).strip().lower(): value for key, value in headers.items()}
    raw = lowered.get(name)
    if raw is None:
        return ""
    return str(raw).strip()


def parse_retry_after_seconds(headers: Mapping[str, Any] | None) -> float | None:
    raw = _header(headers, _RETRY_AFTER)
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    if value < 0 or value > 86_400:
        return None
    return value


def parse_meta_usage(headers: Mapping[str, Any] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    app_usage = _header(headers, _APP_USAGE)
    page_usage = _header(headers, _PAGE_USAGE)
    buc = _header(headers, _BUC_USAGE)
    if app_usage:
        out["x_app_usage"] = app_usage[:500]
    if page_usage:
        out["x_page_usage"] = page_usage[:500]
    if buc:
        out["x_business_use_case_usage"] = buc[:500]
    return out


def parse_openai_rate_limit(headers: Mapping[str, Any] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for key in (
        _OPENAI_REMAINING_REQUESTS,
        _OPENAI_REMAINING_TOKENS,
        _OPENAI_RESET_REQUESTS,
        _OPENAI_RESET_TOKENS,
    ):
        value = _header(headers, key)
        if value:
            out[key.replace("-", "_")] = value[:64]
    return out


def parse_tiktok_request_id(headers: Mapping[str, Any] | None, body: Mapping[str, Any] | None = None) -> str:
    header_id = _header(headers, _TIKTOK_REQUEST_ID)
    if header_id:
        return header_id[:128]
    if isinstance(body, dict):
        return str(body.get("request_id") or "")[:128]
    return ""


def usage_snapshot(headers: Mapping[str, Any] | None, *, provider: str) -> dict[str, str]:
    prov = (provider or "").strip().lower()
    if prov in {"meta", "facebook", "instagram", "whatsapp"}:
        return parse_meta_usage(headers)
    if prov == "openai":
        return parse_openai_rate_limit(headers)
    return {}
