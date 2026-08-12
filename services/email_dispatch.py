"""Idempotent transactional email dispatch over Resend (no client-side sending)."""

from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from services.email_templates_render import render_transactional_email
from services.mail_service import MailResult, public_app_base_url, send_email
from storage.persistent_storage import _DATA_ROOT

logger = logging.getLogger(__name__)

AuthEmailKind = Literal[
    "verify_email",
    "reset_password",
    "password_changed",
    "email_change_confirm",
    "email_changed_notice",
    "welcome",
    "security_notice",
]

BillingEmailKind = Literal[
    "billing_subscription_started",
    "billing_plan_changed",
    "billing_payment_problem",
    "billing_subscription_ended",
    "billing_credits_purchased",
    "billing_refund",
]


@dataclass(frozen=True)
class DispatchResult:
    sent: bool
    reason: str
    provider: str
    message_id: str | None = None
    idempotent_replay: bool = False


class _IdempotencyStore:
    def __init__(self, store_dir: Path | None = None) -> None:
        self._lock = threading.RLock()
        self._dir = store_dir or (Path(_DATA_ROOT) / "email" / "idempotency")
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self._dir / f"{digest}.json"

    def claim_or_get(self, key: str) -> dict[str, Any] | None:
        """Return prior result if key exists; otherwise None (caller should send then put)."""
        path = self._path(key)
        with self._lock:
            if not path.exists():
                return None
            try:
                import json

                loaded = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                return None
            return loaded if isinstance(loaded, dict) else None

    def put(self, key: str, payload: dict[str, Any]) -> None:
        import json

        path = self._path(key)
        with self._lock:
            path.write_text(json.dumps(payload), encoding="utf-8")


_idempotency = _IdempotencyStore()


def _canonical_app_url(path: str, token: str | None = None) -> str:
    base = public_app_base_url().rstrip("/")
    # Force www/linasaibot https canonical host when env points at known production hosts.
    if "linasaibot.com" in base and not base.startswith("https://"):
        base = "https://www.linasaibot.com"
    clean_path = path if path.startswith("/") else f"/{path}"
    if token:
        return f"{base}{clean_path}?token={token}"
    return f"{base}{clean_path}"


def dispatch_template_email(
    *,
    template_id: str,
    to_email: str,
    locale: str | None = None,
    action_path: str | None = None,
    action_token: str | None = None,
    action_url: str | None = None,
    idempotency_key: str | None = None,
    extra_lines: list[str] | None = None,
    tags: list[dict[str, str]] | None = None,
) -> DispatchResult:
    to_addr = (to_email or "").strip().lower()
    if not to_addr or "@" not in to_addr:
        return DispatchResult(sent=False, reason="invalid_recipient", provider="none")

    key = (idempotency_key or "").strip()
    if key:
        prior = _idempotency.claim_or_get(key)
        if prior and prior.get("sent"):
            return DispatchResult(
                sent=True,
                reason="idempotent_replay",
                provider=str(prior.get("provider") or "resend"),
                message_id=prior.get("message_id"),
                idempotent_replay=True,
            )

    url = action_url
    if not url and action_path:
        url = _canonical_app_url(action_path, action_token)

    rendered = render_transactional_email(
        template_id=template_id,
        action_url=url,
        locale=locale,
        extra_lines=extra_lines,
    )
    result: MailResult = send_email(
        to_email=to_addr,
        subject=rendered.subject,
        text_body=rendered.text_body,
        html_body=rendered.html_body,
        tags=tags or [{"name": "template", "value": template_id[:128]}],
        idempotency_key=key or None,
    )
    out = DispatchResult(
        sent=bool(result.sent),
        reason=result.reason,
        provider=result.provider,
        message_id=getattr(result, "message_id", None),
    )
    if key and out.sent:
        _idempotency.put(
            key,
            {
                "sent": True,
                "provider": out.provider,
                "message_id": out.message_id,
                "template_id": template_id,
                "created_at": time.time(),
            },
        )
    if not out.sent:
        logger.info(
            "[email_dispatch] not_sent template=%s reason=%s provider=%s",
            template_id,
            out.reason,
            out.provider,
        )
    return out


def send_verify_email(*, to_email: str, raw_token: str, locale: str | None = None, user_id: str = "") -> DispatchResult:
    return dispatch_template_email(
        template_id="verify_email",
        to_email=to_email,
        locale=locale,
        action_path="/verify-email",
        action_token=raw_token,
        idempotency_key=f"verify:{user_id}:{hashlib.sha256(raw_token.encode()).hexdigest()[:24]}",
    )


def send_reset_password_email(
    *, to_email: str, raw_token: str, locale: str | None = None, user_id: str = ""
) -> DispatchResult:
    return dispatch_template_email(
        template_id="reset_password",
        to_email=to_email,
        locale=locale,
        action_path="/reset-password",
        action_token=raw_token,
        idempotency_key=f"reset:{user_id}:{hashlib.sha256(raw_token.encode()).hexdigest()[:24]}",
    )


def send_password_changed_email(*, to_email: str, locale: str | None = None, user_id: str = "") -> DispatchResult:
    return dispatch_template_email(
        template_id="password_changed",
        to_email=to_email,
        locale=locale,
        action_path="/login",
        idempotency_key=f"pwchanged:{user_id}:{int(time.time() // 60)}",
    )


def send_email_change_confirm(
    *, to_email: str, raw_token: str, locale: str | None = None, user_id: str = ""
) -> DispatchResult:
    return dispatch_template_email(
        template_id="email_change_confirm",
        to_email=to_email,
        locale=locale,
        action_path="/verify-email",
        action_token=raw_token,
        idempotency_key=f"emailchg:{user_id}:{hashlib.sha256(raw_token.encode()).hexdigest()[:24]}",
    )


def send_email_changed_notice(*, to_email: str, locale: str | None = None, user_id: str = "") -> DispatchResult:
    return dispatch_template_email(
        template_id="email_changed_notice",
        to_email=to_email,
        locale=locale,
        action_path="/login",
        idempotency_key=f"emailchgnotice:{user_id}:{int(time.time() // 300)}",
    )


def send_welcome_email(*, to_email: str, locale: str | None = None, user_id: str = "") -> DispatchResult:
    return dispatch_template_email(
        template_id="welcome",
        to_email=to_email,
        locale=locale,
        action_path="/login",
        idempotency_key=f"welcome:{user_id}",
    )


def send_billing_email(
    *,
    kind: BillingEmailKind,
    to_email: str,
    locale: str | None = None,
    tenant_id: str = "",
    event_id: str = "",
    extra_lines: list[str] | None = None,
) -> DispatchResult:
    """Billing transactional interface — callers supply durable event_id for idempotency."""
    key = f"billing:{kind}:{tenant_id}:{event_id}".strip(":")
    return dispatch_template_email(
        template_id=kind,
        to_email=to_email,
        locale=locale,
        action_path="/",
        idempotency_key=key if event_id else None,
        extra_lines=extra_lines,
        tags=[{"name": "category", "value": "billing"}],
    )


def oauth_email_policy(*, provider: str, email_verified_by_provider: bool) -> dict[str, Any]:
    """Architecture helper: OAuth identities skip password-verify email when already verified."""
    prov = (provider or "").strip().lower()
    if prov not in {"apple", "google"}:
        return {"provider": prov, "skip_verification_email": False, "reason": "unknown_provider"}
    if email_verified_by_provider:
        return {
            "provider": prov,
            "skip_verification_email": True,
            "reason": "provider_verified_identity",
            "accepts_private_relay": prov == "apple",
        }
    return {"provider": prov, "skip_verification_email": False, "reason": "provider_unverified"}


def mail_runtime_provider() -> str:
    if (os.getenv("RESEND_API_KEY") or os.getenv("RESEND_API_KEY_SENDING") or "").strip():
        return "resend"
    if (os.getenv("SMTP_HOST") or "").strip():
        return "smtp"
    return "none"
