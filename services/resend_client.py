"""Minimal Resend HTTP client for transactional email (server-side only)."""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

RESEND_API_BASE = "https://api.resend.com"


@dataclass(frozen=True)
class ResendSendResult:
    ok: bool
    reason: str
    message_id: str | None = None
    status_code: int | None = None


def resend_api_key() -> str:
    """Runtime key — prefer sending-only when present."""
    for key in ("RESEND_API_KEY", "RESEND_API_KEY_SENDING"):
        value = (os.getenv(key) or "").strip()
        if value:
            return value
    return ""


def resend_configured() -> bool:
    return bool(resend_api_key())


def default_from_address() -> str:
    return (os.getenv("RESEND_FROM") or os.getenv("MAIL_FROM") or "Linas AI <no-reply@linasaibot.com>").strip()


def default_reply_to() -> str | None:
    value = (os.getenv("RESEND_REPLY_TO") or "support@linasaibot.com").strip()
    return value or None


def send_resend_email(
    *,
    to_email: str,
    subject: str,
    text_body: str,
    html_body: str | None = None,
    from_addr: str | None = None,
    reply_to: str | None = None,
    tags: list[dict[str, str]] | None = None,
    headers: dict[str, str] | None = None,
    idempotency_key: str | None = None,
) -> ResendSendResult:
    """Send one email via Resend. Never logs API keys or full bodies."""
    api_key = resend_api_key()
    if not api_key:
        return ResendSendResult(ok=False, reason="resend_not_configured")

    to_addr = (to_email or "").strip().lower()
    if not to_addr or "@" not in to_addr:
        return ResendSendResult(ok=False, reason="invalid_recipient")

    payload: dict[str, Any] = {
        "from": (from_addr or default_from_address()).strip(),
        "to": [to_addr],
        "subject": subject,
        "text": text_body,
    }
    if html_body:
        payload["html"] = html_body
    rt = reply_to if reply_to is not None else default_reply_to()
    if rt:
        payload["reply_to"] = rt
    if tags:
        payload["tags"] = tags
    if headers:
        payload["headers"] = headers

    req_headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "LinasAI-Server/1.0",
    }
    if idempotency_key:
        req_headers["Idempotency-Key"] = idempotency_key[:256]

    request = urllib.request.Request(
        f"{RESEND_API_BASE}/emails",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers=req_headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as resp:
            raw = resp.read().decode("utf-8")
            data = json.loads(raw) if raw else {}
            message_id = str(data.get("id") or "") or None
            return ResendSendResult(ok=True, reason="ok", message_id=message_id, status_code=resp.status)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:300]
        logger.warning(
            "[resend] send failed status=%s type=%s body_len=%s",
            exc.code,
            type(exc).__name__,
            len(body),
        )
        return ResendSendResult(ok=False, reason="resend_http_error", status_code=exc.code)
    except Exception as exc:
        logger.warning("[resend] send failed type=%s", type(exc).__name__)
        return ResendSendResult(ok=False, reason="resend_error")
