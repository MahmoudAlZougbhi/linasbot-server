"""One scheduler pass per interval across the two production nodes.

The Redis key stays until its TTL after a finished pass. Releasing it on
success is what let the peer node repeat the same minute. A raised error
releases the key so the peer can take that cycle.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from services.scale.durable_event_claim import release_job_lock, try_acquire_job_lock


@contextmanager
def job_interval_lock(job_id: str, *, ttl_seconds: float) -> Iterator[bool]:
    if not try_acquire_job_lock(job_id, ttl_seconds=ttl_seconds):
        yield False
        return
    failed = False
    try:
        yield True
    except BaseException:
        failed = True
        raise
    finally:
        if failed:
            release_job_lock(job_id)
