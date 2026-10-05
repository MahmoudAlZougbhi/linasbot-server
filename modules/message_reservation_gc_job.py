"""Sweep stale Customer AI message reservations."""

from __future__ import annotations


async def run_message_reservation_gc_job() -> None:
    from services.billing.membership.reservation_gc import run_reservation_gc
    from services.scale.job_interval_lock import job_interval_lock

    # 14 minutes of 15, so an offset peer does not sweep the same rows.
    with job_interval_lock("message_reservation_gc", ttl_seconds=840) as acquired:
        if not acquired:
            return
        run_reservation_gc()
