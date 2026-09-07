"""TikTok Marketing API (advertiser) settings. Separate from Accounts OAuth."""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse

from services.tiktok_business.config import get_tiktok_settings

TIKTOK_ADS_AUTHORIZE_URL = "https://ads.tiktok.com/marketing_api/auth"
EXPECTED_ADS_REDIRECT_URI = "https://www.linasaibot.com/oauth/tiktok/ads/callback"
PROBE_COOLDOWN_SECONDS = 6 * 60 * 60
MANUAL_REFRESH_MIN_SECONDS = 10 * 60


def _strip(name: str) -> str:
    return (os.getenv(name) or "").strip()


@dataclass(frozen=True)
class TikTokAdsSettings:
    app_id: str
    secret: str
    redirect_uri: str
    authorize_url: str
    configured: bool


def tiktok_ads_redirect_uri() -> str:
    return _strip("TIKTOK_ADS_REDIRECT_URI") or EXPECTED_ADS_REDIRECT_URI


def get_tiktok_ads_settings() -> TikTokAdsSettings:
    accounts = get_tiktok_settings()
    app_id = _strip("TIKTOK_ADS_APP_ID") or accounts.client_key
    secret = _strip("TIKTOK_ADS_APP_SECRET") or accounts.client_secret
    redirect = tiktok_ads_redirect_uri()
    parsed = urlparse(redirect)
    if parsed.scheme != "https" or not parsed.netloc:
        redirect = EXPECTED_ADS_REDIRECT_URI
    return TikTokAdsSettings(
        app_id=app_id,
        secret=secret,
        redirect_uri=redirect,
        authorize_url=TIKTOK_ADS_AUTHORIZE_URL,
        configured=bool(app_id and secret),
    )


def require_tiktok_ads_settings() -> TikTokAdsSettings:
    from services.tiktok_business.errors import TikTokNotConfiguredError

    settings = get_tiktok_ads_settings()
    if not settings.configured:
        raise TikTokNotConfiguredError(
            "TikTok Marketing credentials are not configured. Set TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET."
        )
    return settings
