"""TikTok Business API configuration. Credentials missing → fail closed for OAuth/API."""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse

TIKTOK_AUTHORIZE_URL = "https://www.tiktok.com/v2/auth/authorize/"
TIKTOK_API_BASE = "https://business-api.tiktok.com/open_api/v1.3"
TIKTOK_API_HOST = "business-api.tiktok.com"
EXPECTED_REDIRECT_URI = "https://www.linasaibot.com/oauth/tiktok/callback"
EXPECTED_WEBHOOK_URL = "https://www.linasaibot.com/webhooks/tiktok"

# TikTok Accounts API scopes only (display names → API scope strings).
# Do not request insights, publish, advertising, ad comments, mentions, benchmark, discovery, or messaging.
REQUESTED_SCOPES: tuple[str, ...] = (
    "user.info.basic",  # Get Account User Basic Info
    "video.list",  # Get Account Media
    "comment.list",  # Get Account Comment
    "comment.list.manage",  # Manage Account Comment
    "biz.spark.auth",  # Auth Code Management
)

COMMENT_READ_SCOPES = frozenset({"comment.list"})
COMMENT_MANAGE_SCOPES = frozenset({"comment.list.manage"})
MEDIA_SCOPES = frozenset({"video.list"})
PROFILE_SCOPES = frozenset({"user.info.basic"})
# Business Messaging is NOT requested. Presence on a token is detected, never assumed.
MESSAGING_READ_SCOPES = frozenset({"message.list.read"})
MESSAGING_SEND_SCOPES = frozenset({"message.list.send", "message.list.manage"})

RETRYABLE_TIKTOK_CODES = frozenset({40100, 40130, 40700, 50000, 50001})
TOKEN_EXPIRED_TIKTOK_CODES = frozenset({40104, 40105})
OAUTH_STATE_TTL_SECONDS = 10 * 60
WEBHOOK_TIMESTAMP_TOLERANCE_SECONDS = 300
SYNC_LEASE_SECONDS = 90
COMMENT_SYNC_INTERVAL_SECONDS = 180
MAX_VIDEOS_PER_SYNC = 20
MAX_COMMENT_PAGES_PER_VIDEO = 3
TOKEN_REFRESH_SKEW_SECONDS = 2 * 60 * 60


def _strip(name: str) -> str:
    return (os.getenv(name) or "").strip()


@dataclass(frozen=True)
class TikTokBusinessSettings:
    client_key: str
    client_secret: str
    redirect_uri: str
    webhook_callback_url: str
    api_base: str
    configured: bool


def tiktok_redirect_uri() -> str:
    return _strip("TIKTOK_REDIRECT_URI") or EXPECTED_REDIRECT_URI


def tiktok_webhook_callback_url() -> str:
    return _strip("TIKTOK_WEBHOOK_CALLBACK_URL") or EXPECTED_WEBHOOK_URL


def get_tiktok_settings() -> TikTokBusinessSettings:
    client_key = _strip("TIKTOK_CLIENT_KEY")
    client_secret = _strip("TIKTOK_CLIENT_SECRET")
    redirect = tiktok_redirect_uri()
    webhook = tiktok_webhook_callback_url()
    parsed = urlparse(redirect)
    if parsed.scheme != "https" or not parsed.netloc:
        redirect = EXPECTED_REDIRECT_URI
    return TikTokBusinessSettings(
        client_key=client_key,
        client_secret=client_secret,
        redirect_uri=redirect,
        webhook_callback_url=webhook,
        api_base=TIKTOK_API_BASE,
        configured=bool(client_key and client_secret),
    )


def require_tiktok_settings() -> TikTokBusinessSettings:
    from services.tiktok_business.errors import TikTokNotConfiguredError

    settings = get_tiktok_settings()
    if not settings.configured:
        raise TikTokNotConfiguredError(
            "TikTok Business credentials are not configured. Set TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET."
        )
    return settings


def tiktok_config_key_presence() -> dict[str, bool]:
    """Presence-only operator checklist — never secret values."""

    keys = (
        "TIKTOK_CLIENT_KEY",
        "TIKTOK_CLIENT_SECRET",
        "TIKTOK_REDIRECT_URI",
        "TIKTOK_WEBHOOK_CALLBACK_URL",
        "META_CREDENTIAL_ENCRYPTION_KEY",
        "LINAS_WHATSAPP_DATABASE_URL",
        "DATABASE_URL",
        "PUBLIC_URL",
    )
    return {k: bool(_strip(k)) for k in keys}


def parse_scope_string(raw: str | None) -> tuple[str, ...]:
    parts = [p.strip() for p in str(raw or "").replace(" ", ",").split(",") if p.strip()]
    # Preserve order, drop duplicates.
    seen: set[str] = set()
    out: list[str] = []
    for part in parts:
        if part not in seen:
            seen.add(part)
            out.append(part)
    return tuple(out)
