"""SMTP mail delivery for auth flows (password reset, email verification).

Configure via env. When SMTP is not configured, messages are not faked as sent —
callers receive ``sent=False`` with a clear reason. Local/dev may log the link
when ``MAIL_LOG_LINKS=true`` (never enable in production with real tokens logged
to shared logs if avoidable).
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
    provider: str = "smtp"


def mail_configured() -> bool:
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
    }


def send_email(*, to_email: str, subject: str, text_body: str, html_body: str | None = None) -> MailResult:
    """Send a plain/HTML email. Never raises for delivery failure — returns MailResult."""
    to_addr = (to_email or "").strip().lower()
    if not to_addr or "@" not in to_addr:
        return MailResult(sent=False, reason="invalid_recipient")

    settings = _smtp_settings()
    if not settings["host"] or not settings["from_addr"]:
        if (os.getenv("MAIL_LOG_LINKS") or "").strip().lower() in {"1", "true", "yes", "on"}:
            logger.info(
                "[mail] SMTP not configured; link logged for local testing subject=%s to=%s body=%s",
                subject,
                to_addr,
                text_body[:500],
            )
            return MailResult(sent=False, reason="smtp_not_configured_logged", provider="log")
        return MailResult(sent=False, reason="smtp_not_configured")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings["from_addr"]
    msg["To"] = to_addr
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
        return MailResult(sent=True, reason="ok")
    except Exception as exc:
        logger.warning("[mail] send failed type=%s", type(exc).__name__)
        return MailResult(sent=False, reason="smtp_error")


def public_app_base_url() -> str:
    """Public site origin for email links (no trailing slash)."""
    for key in ("PUBLIC_URL", "PUBLIC_APP_URL", "APP_PUBLIC_URL"):
        raw = (os.getenv(key) or "").strip().rstrip("/")
        if raw:
            return raw
    return "https://www.linasaibot.com"
