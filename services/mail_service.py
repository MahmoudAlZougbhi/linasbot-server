"""Transactional mail delivery — Resend primary when configured; SMTP only if Resend unset.

No silent fallback from Resend failure to SMTP (owner rule). When neither transport
is configured, callers receive sent=False with a clear reason.
"""

from __future__ import annotations

import logging
import os
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MailResult:
    sent: bool
    reason: str
    provider: str = "none"
    message_id: str | None = None


def mail_configured() -> bool:
    from services.resend_client import resend_configured

    if resend_configured():
        return True
    host = (os.getenv("SMTP_HOST") or "").strip()
    from_addr = (os.getenv("SMTP_FROM") or os.getenv("MAIL_FROM") or "").strip()
    return bool(host and from_addr)


def _smtp_settings() -> dict[str, Any]:
    return {
        "host": (os.getenv("SMTP_HOST") or "").strip(),
        "port": int(os.getenv("SMTP_PORT") or "587"),
        "user": (os.getenv("SMTP_USER") or "").strip(),
        "password": (os.getenv("SMTP_PASSWORD") or "").strip(),
        "from_addr": (os.getenv("SMTP_FROM") or os.getenv("MAIL_FROM") or "").strip(),
        "use_tls": (os.getenv("SMTP_USE_TLS") or "true").strip().lower() in {"1", "true", "yes", "on"},
        "use_ssl": (os.getenv("SMTP_USE_SSL") or "").strip().lower() in {"1", "true", "yes", "on"},
        "reply_to": (os.getenv("RESEND_REPLY_TO") or os.getenv("MAIL_REPLY_TO") or "support@linasaibot.com").strip(),
    }


def _send_smtp(*, to_email: str, subject: str, text_body: str, html_body: str | None) -> MailResult:
    settings = _smtp_settings()
    if not settings["host"] or not settings["from_addr"]:
        if (os.getenv("MAIL_LOG_LINKS") or "").strip().lower() in {"1", "true", "yes", "on"}:
            logger.info(
                "[mail] SMTP not configured; link logged for local testing subject=%s to=%s body=%s",
                subject,
                to_email,
                text_body[:500],
            )
            return MailResult(sent=False, reason="smtp_not_configured_logged", provider="log")
        return MailResult(sent=False, reason="smtp_not_configured", provider="smtp")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings["from_addr"]
    msg["To"] = to_email
    if settings["reply_to"]:
        msg["Reply-To"] = settings["reply_to"]
    msg.set_content(text_body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")

    try:
        if settings["use_ssl"]:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(settings["host"], settings["port"], context=context, timeout=20) as smtp:
                if settings["user"]:
                    smtp.login(settings["user"], settings["password"])
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(settings["host"], settings["port"], timeout=20) as smtp:
                if settings["use_tls"]:
                    smtp.starttls(context=ssl.create_default_context())
                if settings["user"]:
                    smtp.login(settings["user"], settings["password"])
                smtp.send_message(msg)
        return MailResult(sent=True, reason="ok", provider="smtp")
    except Exception as exc:
        logger.warning("[mail] smtp send failed type=%s", type(exc).__name__)
        return MailResult(sent=False, reason="smtp_error", provider="smtp")


def send_email(
    *,
    to_email: str,
    subject: str,
    text_body: str,
    html_body: str | None = None,
    tags: list[dict[str, str]] | None = None,
    idempotency_key: str | None = None,
) -> MailResult:
    """Send plain/HTML email. Never raises for delivery failure — returns MailResult."""
    to_addr = (to_email or "").strip().lower()
    if not to_addr or "@" not in to_addr:
        return MailResult(sent=False, reason="invalid_recipient")

    from services.resend_client import resend_configured, send_resend_email

    if resend_configured():
        result = send_resend_email(
            to_email=to_addr,
            subject=subject,
            text_body=text_body,
            html_body=html_body,
            tags=tags,
            idempotency_key=idempotency_key,
        )
        return MailResult(
            sent=bool(result.ok),
            reason=result.reason,
            provider="resend",
            message_id=result.message_id,
        )

    return _send_smtp(to_email=to_addr, subject=subject, text_body=text_body, html_body=html_body)


def public_app_base_url() -> str:
    """Public site origin for email links (no trailing slash)."""
    for key in ("PUBLIC_URL", "PUBLIC_APP_URL", "APP_PUBLIC_URL"):
        raw = (os.getenv(key) or "").strip().rstrip("/")
        if raw:
            return raw
    return "https://www.linasaibot.com"
