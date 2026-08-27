"""Queue / Redis configuration from environment (never hardcoded hosts/secrets)."""

from __future__ import annotations

import os
from typing import Final

QUEUE_NAMES: Final[tuple[str, ...]] = (
    "high_priority",  # DMs, WhatsApp, Web Chat, operator outbound
    "interactive",  # owner async work
    "background",  # public comments, polling, reconcile, TikTok outbound
    "expensive",  # creative image/video
)

DEFAULT_CONCURRENCY: Final[dict[str, int]] = {
    "high_priority": int(os.getenv("LINAS_QUEUE_CONCURRENCY_HIGH", "8")),
    "interactive": int(os.getenv("LINAS_QUEUE_CONCURRENCY_INTERACTIVE", "4")),
    "background": int(os.getenv("LINAS_QUEUE_CONCURRENCY_BACKGROUND", "2")),
    "expensive": int(os.getenv("LINAS_QUEUE_CONCURRENCY_EXPENSIVE", "1")),
}

DEFAULT_JOB_TIMEOUT_SECONDS: Final[int] = int(os.getenv("LINAS_QUEUE_JOB_TIMEOUT_SECONDS", "300"))
DEFAULT_MAX_ATTEMPTS: Final[int] = int(os.getenv("LINAS_QUEUE_MAX_ATTEMPTS", "5"))
DEFAULT_TENANT_INFLIGHT: Final[int] = int(os.getenv("LINAS_QUEUE_TENANT_INFLIGHT", "4"))
HEARTBEAT_TTL_SECONDS: Final[int] = int(os.getenv("LINAS_QUEUE_HEARTBEAT_TTL_SECONDS", "30"))


def lease_ttl_seconds() -> int:
    """Worker-liveness window only. Not a maximum job duration.

    Default 20s covers several 3s heartbeats plus event-loop lag. Luna/Tera may
    run for minutes while the dedicated heartbeat thread keeps this key alive.
    """
    raw = (os.getenv("LINAS_QUEUE_LEASE_TTL_SECONDS") or "20").strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 20


def lease_heartbeat_seconds() -> float:
    raw = (os.getenv("LINAS_QUEUE_LEASE_HEARTBEAT_SECONDS") or "3").strip()
    try:
        return max(0.05, float(raw))
    except ValueError:
        return 3.0


def redis_url() -> str | None:
    raw = (os.getenv("REDIS_URL") or os.getenv("LINAS_REDIS_URL") or "").strip()
    return raw or None


def is_production_env() -> bool:
    env = (os.getenv("ENVIRONMENT") or os.getenv("ENV") or "").strip().lower()
    return env in {"prod", "production"}


def redis_required() -> bool:
    """Hard-require Redis when durable queues are activated.

    Not implied by ENVIRONMENT=production alone — set LINAS_REQUIRE_REDIS=true
    (or LINAS_ENABLE_DURABLE_QUEUES=true) during Phase 2 activation so current
    production stays ready until Redis/workers are wired.
    """
    for key in ("LINAS_REQUIRE_REDIS", "LINAS_ENABLE_DURABLE_QUEUES"):
        if (os.getenv(key) or "").strip().lower() in {"1", "true", "yes", "on"}:
            return True
    return False


def key_prefix() -> str:
    return (os.getenv("LINAS_QUEUE_KEY_PREFIX") or "linas:q").strip() or "linas:q"
