"""Sweep stale Customer AI message reservations."""

from __future__ import annotations


async def run_message_reservation_gc_job() -> None:
    from services.durable_event_claim import release_job_lock, try_acquire_job_lock
    from services.membership.reservation_gc import run_reservation_gc

    if not try_acquire_job_lock("message_reservation_gc", ttl_seconds=50):
        return
    try:
        run_reservation_gc()
    finally:
        release_job_lock("message_reservation_gc")
