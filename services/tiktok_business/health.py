"""Health/readiness snippet for TikTok Business — capability without secret values."""

from __future__ import annotations

from typing import Any

from services.tiktok_business.config import get_tiktok_settings, tiktok_config_key_presence, tiktok_redirect_uri


def tiktok_business_readiness() -> dict[str, Any]:
    settings = get_tiktok_settings()
    return {
        "ok": True,
        "configured": settings.configured,
        "required": False,
        "redirect_uri": tiktok_redirect_uri() if settings.configured else None,
        "comments_supported_in_code": True,
        "messaging_supported_in_code": True,
        "messaging_requires_tiktok_approval": True,
        "config_keys_present": tiktok_config_key_presence(),
    }
