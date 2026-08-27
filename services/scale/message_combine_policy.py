"""When to defer combine+AI to a delayed worker instead of a process-local timer."""

from __future__ import annotations

import os


def _truthy(name: str) -> bool:
    return (os.getenv(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def distributed_combine_enabled() -> bool:
    """True when Redis is the source of truth for pending DM chunks."""
    if _truthy("LINAS_DISTRIBUTED_COMBINE"):
        return True
    try:
        from services.queues.config import redis_required

        return redis_required()
    except Exception:
        return False


def durable_flush_jobs_enabled() -> bool:
    """True when combine wait must not occupy an inbound worker slot."""
    if not distributed_combine_enabled():
        return False
    try:
        from services.omnichannel.enqueue import queue_is_durable

        return queue_is_durable()
    except Exception:
        return False


def combine_delay_seconds(override: float | None) -> float:
    if override is not None:
        return max(0.0, float(override))
    import config

    return max(0.0, float(getattr(config, "MESSAGE_COMBINING_DELAY", 3.0)))
