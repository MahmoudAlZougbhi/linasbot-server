"""Request-draft lifetime. Off by default, so drafts still never expire."""

from __future__ import annotations

from datetime import datetime, timedelta

from services.platform.feature_flags import flag_enabled

DEFAULT_DRAFT_TTL_DAYS = 30
MIN_DRAFT_TTL_DAYS = 7


def draft_ttl_days(tenant_days: int | None = None) -> int:
    """0 means do not expire. A configured value is never below 7 days."""
    if not flag_enabled("draft_ttl"):
        return 0
    days = DEFAULT_DRAFT_TTL_DAYS if tenant_days is None else int(tenant_days)
    return max(MIN_DRAFT_TTL_DAYS, days)


def draft_is_expired(updated_at: datetime, *, now: datetime, tenant_days: int | None = None) -> bool:
    days = draft_ttl_days(tenant_days)
    if days <= 0:
        return False
    return updated_at < now - timedelta(days=days)
