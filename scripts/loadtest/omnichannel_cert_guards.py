"""Hard safety guards for isolated omnichannel certification."""

from __future__ import annotations

import os
import re
from urllib.parse import urlparse

STAGING_FLAG = "LINAS_OMNI_CERT_STAGING"
TEST_TENANT_PREFIX = "omni-cert-"
MAX_EVENTS_PER_MINUTE = 4_000
MAX_DURATION_SECONDS = 25 * 60 * 60
MAX_ESTIMATED_OPENAI_USD = 5.0
ABORT_ERROR_RATIO = 0.01
ABORT_LOST_EVENTS = 1

PRODUCTION_HOSTS = frozenset(
    {
        "www.linasaibot.com",
        "linasaibot.com",
        "graph.facebook.com",
        "graph.instagram.com",
        "business-api.tiktok.com",
        "api.openai.com",
        "graph.whatsapp.com",
    }
)
ALLOWED_HOSTS = frozenset(
    {
        "127.0.0.1",
        "localhost",
        "omnichannel-cert-postgres",
        "omnichannel-cert-redis",
        "omnichannel-cert-api",
        "omnichannel-cert-api-a",
        "omnichannel-cert-api-b",
    }
)
_PHONE = re.compile(r"\+?\d[\d\s\-()]{7,}\d")
_EMAIL = re.compile(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", re.I)


class CertGuardError(PermissionError):
    """Certification refused because a safety guard failed."""


def hostname_of(url: str) -> str:
    raw = (url or "").strip()
    if "://" not in raw:
        raw = f"http://{raw}"
    return (urlparse(raw).hostname or "").strip().lower()


def sanitize_text(value: str, *, limit: int = 64) -> str:
    text = _EMAIL.sub("[redacted-email]", _PHONE.sub("[redacted-phone]", str(value or "")))
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > limit:
        return text[:12] + "…"
    return text


def assert_staging_cert_allowed(
    *,
    target_url: str,
    tenant_id: str,
    events_per_minute: int,
    duration_seconds: int,
    estimated_openai_usd: float = 0.0,
) -> None:
    if (os.getenv(STAGING_FLAG) or "").strip() != "1":
        raise CertGuardError("LINAS_OMNI_CERT_STAGING=1 is required")
    host = hostname_of(target_url)
    if not host:
        raise CertGuardError("cert_target_host_missing")
    if host in PRODUCTION_HOSTS or host.endswith(".linasaibot.com"):
        raise CertGuardError("production_host_rejected")
    if host not in ALLOWED_HOSTS and not host.endswith(".omnichannel-cert.local"):
        raise CertGuardError("host_not_allowlisted")
    if not str(tenant_id or "").startswith(TEST_TENANT_PREFIX):
        raise CertGuardError("test_tenant_prefix_required")
    if int(events_per_minute) > MAX_EVENTS_PER_MINUTE:
        raise CertGuardError("event_rate_exceeds_cert_cap")
    if int(duration_seconds) > MAX_DURATION_SECONDS:
        raise CertGuardError("duration_exceeds_cert_cap")
    if float(estimated_openai_usd) > MAX_ESTIMATED_OPENAI_USD:
        raise CertGuardError("openai_cost_exceeds_authorized_budget")


def should_abort(*, lost: int, errors: int, accepted: int) -> str | None:
    if int(lost) >= ABORT_LOST_EVENTS:
        return "lost_events"
    if accepted > 0 and (errors / accepted) > ABORT_ERROR_RATIO:
        return "error_ratio"
    return None
