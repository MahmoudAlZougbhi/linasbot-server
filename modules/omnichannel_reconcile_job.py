"""Periodic reconcile for omnichannel inbound ledger and outbound outbox."""

from __future__ import annotations

import asyncio

from services.scale.job_interval_lock import job_interval_lock


def _run_omnichannel_reconcile_job_sync() -> None:
    with job_interval_lock("omnichannel_reconcile", ttl_seconds=50) as acquired:
        if not acquired:
            return
        try:
            from services.integrations.omnichannel.reconcile import reconcile_omnichannel

            result = reconcile_omnichannel(older_than_seconds=45.0)
            examined = int(result.get("examined") or 0)
            if examined:
                print(f"[omnichannel-reconcile] examined={examined} actions={len(result.get('actions') or [])}")
        except Exception as exc:
            print(f"[omnichannel-reconcile] failed type={type(exc).__name__}")


async def run_omnichannel_reconcile_job() -> None:
    await asyncio.to_thread(_run_omnichannel_reconcile_job_sync)
