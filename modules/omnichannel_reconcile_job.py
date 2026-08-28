"""Periodic reconcile for omnichannel inbound ledger and outbound outbox."""

from __future__ import annotations

import asyncio

from services.durable_event_claim import release_job_lock, try_acquire_job_lock


def _run_omnichannel_reconcile_job_sync() -> None:
    if not try_acquire_job_lock("omnichannel_reconcile", ttl_seconds=55):
        return
    try:
        from services.omnichannel.reconcile import reconcile_omnichannel

        result = reconcile_omnichannel(older_than_seconds=45.0)
        examined = int(result.get("examined") or 0)
        if examined:
            print(f"[omnichannel-reconcile] examined={examined} actions={len(result.get('actions') or [])}")
    except Exception as exc:
        print(f"[omnichannel-reconcile] failed type={type(exc).__name__}")
    finally:
        release_job_lock("omnichannel_reconcile")


async def run_omnichannel_reconcile_job() -> None:
    await asyncio.to_thread(_run_omnichannel_reconcile_job_sync)
