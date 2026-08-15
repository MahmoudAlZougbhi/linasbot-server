"""Configuration for Instagram API with Instagram Login under Meta App A."""

from __future__ import annotations

import hashlib
import hmac
import os
from dataclasses import dataclass
from typing import Literal

from services.meta_app_registry import APP_A_KEY, get_meta_app_configs

DEFAULT_INSTAGRAM_LOGIN_APP_ID = "1035856539045307"
EXPECTED_INSTAGRAM_LOGIN_REDIRECT_URI = "https://www.linasaibot.com/oauth/instagram/callback"
EXPECTED_INSTAGRAM_LOGIN_WEBHOOK_PATH = "/webhook/instagram-login"
EXPECTED_INSTAGRAM_LOGIN_WEBHOOK_URL = "https://www.linasaibot.com/webhook/instagram-login"
META_INSTAGRAM_GRAPH_BASE_URL = "https://graph.instagram.com"
META_INSTAGRAM_OAUTH_AUTHORIZE_URL = "https://www.instagram.com/oauth/authorize"
META_INSTAGRAM_OAUTH_TOKEN_URL = "https://api.instagram.com/oauth/access_token"

AuthFlow = Literal["facebook_login", "instagram_login"]

# Keep Connect Instagram least-privileged for the App Review surfaces enabled here:
# professional identity, DMs, and comment replies. Content publishing has its own
# permission and must be added through a separate reviewed/reauthorization flow.
META_INSTAGRAM_LOGIN_REQUEST_SCOPES = frozenset(
    {
        "instagram_business_basic",
        "instagram_business_manage_messages",
        "instagram_business_manage_comments",
    }
)

# This product is reviewed and activated as one DM-and-comments surface.  A
# declined comments grant must not replace a previously healthy binding with a
# misleading DM-only connection.
META_INSTAGRAM_LOGIN_REQUIRED_SCOPES = META_INSTAGRAM_LOGIN_REQUEST_SCOPES

# Backward-compatible alias used by existing imports/tests.
META_INSTAGRAM_LOGIN_SCOPES = META_INSTAGRAM_LOGIN_REQUEST_SCOPES


@dataclass(frozen=True)
class InstagramLoginConfigStatus:
    configured: bool
    missing: tuple[str, ...]
    reasons: dict[str, str]


def instagram_login_app_id() -> str:
    return (os.getenv("META_INSTAGRAM_LOGIN_APP_ID") or DEFAULT_INSTAGRAM_LOGIN_APP_ID).strip()


def instagram_login_redirect_uri() -> str:
    return (os.getenv("META_INSTAGRAM_LOGIN_REDIRECT_URI") or EXPECTED_INSTAGRAM_LOGIN_REDIRECT_URI).strip()


def instagram_login_webhook_callback_path() -> str:
    return (os.getenv("META_INSTAGRAM_LOGIN_WEBHOOK_PATH") or EXPECTED_INSTAGRAM_LOGIN_WEBHOOK_PATH).strip()


def instagram_login_webhook_callback_url(public_base: str | None = None) -> str:
    base = (public_base or os.getenv("PUBLIC_URL") or "https://www.linasaibot.com").strip().rstrip("/")
    path = instagram_login_webhook_callback_path()
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{base}{path}"


def instagram_login_webhook_verify_token() -> str:
    return (os.getenv("META_INSTAGRAM_LOGIN_WEBHOOK_VERIFY_TOKEN") or "").strip()


def instagram_login_app_secret() -> str:
    return (os.getenv("META_INSTAGRAM_LOGIN_APP_SECRET") or "").strip()


def instagram_login_config_status() -> InstagramLoginConfigStatus:
    """Fail-closed readiness for Instagram Login; never falls back to App A/Facebook secrets."""

    missing: list[str] = []
    reasons: dict[str, str] = {}
    app = get_meta_app_configs()[APP_A_KEY]
    if not app.enabled:
        missing.append("META_APP_A_ENABLED")
        reasons["META_APP_A_ENABLED"] = "Meta App A must be enabled"
    app_id = instagram_login_app_id()
    if not app_id.isdigit() or app_id != DEFAULT_INSTAGRAM_LOGIN_APP_ID:
        missing.append("META_INSTAGRAM_LOGIN_APP_ID")
        reasons["META_INSTAGRAM_LOGIN_APP_ID"] = f"Instagram Login App ID must be {DEFAULT_INSTAGRAM_LOGIN_APP_ID}"
    if instagram_login_redirect_uri() != EXPECTED_INSTAGRAM_LOGIN_REDIRECT_URI:
        missing.append("META_INSTAGRAM_LOGIN_REDIRECT_URI")
        reasons["META_INSTAGRAM_LOGIN_REDIRECT_URI"] = (
            f"OAuth redirect URI must be {EXPECTED_INSTAGRAM_LOGIN_REDIRECT_URI}"
        )
    if instagram_login_webhook_callback_path() != EXPECTED_INSTAGRAM_LOGIN_WEBHOOK_PATH:
        missing.append("META_INSTAGRAM_LOGIN_WEBHOOK_PATH")
        reasons["META_INSTAGRAM_LOGIN_WEBHOOK_PATH"] = f"Webhook path must be {EXPECTED_INSTAGRAM_LOGIN_WEBHOOK_PATH}"
    if instagram_login_webhook_callback_url() != EXPECTED_INSTAGRAM_LOGIN_WEBHOOK_URL:
        missing.append("PUBLIC_URL")
        reasons["PUBLIC_URL"] = f"Instagram webhook URL must be {EXPECTED_INSTAGRAM_LOGIN_WEBHOOK_URL}"
    secret = instagram_login_app_secret()
    if not secret:
        missing.append("META_INSTAGRAM_LOGIN_APP_SECRET")
        reasons["META_INSTAGRAM_LOGIN_APP_SECRET"] = (
            "Instagram App Secret from Instagram API setup is required (no App A fallback)"
        )
    verify_token = instagram_login_webhook_verify_token()
    if not verify_token:
        missing.append("META_INSTAGRAM_LOGIN_WEBHOOK_VERIFY_TOKEN")
        reasons["META_INSTAGRAM_LOGIN_WEBHOOK_VERIFY_TOKEN"] = (
            "Dedicated Instagram Login webhook verify token is required"
        )
    return InstagramLoginConfigStatus(
        configured=not missing,
        missing=tuple(missing),
        reasons=reasons,
    )


DEFAULT_INSTAGRAM_LOGIN_REFRESH_LEAD_DAYS = 7


def instagram_login_refresh_lead_seconds() -> int:
    raw = (
        os.getenv("META_INSTAGRAM_LOGIN_REFRESH_LEAD_DAYS") or str(DEFAULT_INSTAGRAM_LOGIN_REFRESH_LEAD_DAYS)
    ).strip()
    try:
        days = max(1, int(raw))
    except ValueError:
        days = DEFAULT_INSTAGRAM_LOGIN_REFRESH_LEAD_DAYS
    return days * 24 * 3600


def instagram_login_configured() -> bool:
    return instagram_login_config_status().configured


def verify_instagram_login_challenge_token(candidate: str | None) -> bool:
    expected = instagram_login_webhook_verify_token()
    if not expected:
        return False
    return hmac.compare_digest(candidate or "", expected)


def verify_instagram_login_webhook_signature(raw_body: bytes, signature_header: str | None) -> bool:
    secret = instagram_login_app_secret()
    if not secret or not raw_body or not signature_header or not signature_header.startswith("sha256="):
        return False
    received = signature_header[len("sha256=") :].strip().lower()
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(received, expected)


def required_scopes_for_binding(*, channel: str, auth_flow: str) -> frozenset[str]:
    from services.meta_app_registry import META_CHANNEL_SCOPES

    if auth_flow == "instagram_login" and channel == "instagram":
        return META_INSTAGRAM_LOGIN_REQUIRED_SCOPES
    return META_CHANNEL_SCOPES[channel]  # type: ignore[index]
