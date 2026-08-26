"""Distributed Meta comment send cap. Process RAM is never the authority."""

from __future__ import annotations

from services.rate_limit_service import RateLimitService, RateLimitUnavailableError

_COMMENT_RATE_WINDOW_SECONDS = 60
_COMMENT_RATE_LIMIT_PER_ASSET = 30
_limiter = RateLimitService()


def comment_send_allowed(*, tenant_id: str, app_key: str, channel: str, asset_id: str) -> bool:
    key = f"meta-comment:{tenant_id}:{app_key}:{channel}:{asset_id}"
    try:
        allowed, _retry = _limiter.hit(
            key,
            limit=_COMMENT_RATE_LIMIT_PER_ASSET,
            window_seconds=_COMMENT_RATE_WINDOW_SECONDS,
        )
    except RateLimitUnavailableError:
        return False
    return bool(allowed)


def configure_comment_limiter(service: RateLimitService) -> None:
    global _limiter
    _limiter = service
