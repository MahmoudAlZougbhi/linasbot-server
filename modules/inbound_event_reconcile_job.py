"""Periodic reconcile for durable inbound Meta events."""

from __future__ import annotations

from services.durable_event_claim import release_job_lock, try_acquire_job_lock


async def run_inbound_event_reconcile_job() -> None:
    if not try_acquire_job_lock("inbound_event_reconcile", ttl_seconds=55):
        return
    try:
        from services.scale.inbound_event_reconcile import reconcile_stuck_inbound_events

        result = reconcile_stuck_inbound_events(older_than_seconds=45.0)
        examined = int(result.get("examined") or 0)
        missing = int(result.get("unexplained_missing_events") or 0)
        if examined or missing:
            print(
                f"[inbound-reconcile] examined={examined} "
                f"actions={len(result.get('actions') or [])} "
                f"unexplained_missing={missing}"
            )
        from services.omnichannel.reconcile import reconcile_omnichannel

        omni = reconcile_omnichannel(older_than_seconds=45.0)
        if int(omni.get("examined") or 0):
            print(f"[omnichannel-reconcile] examined={omni.get('examined')} actions={len(omni.get('actions') or [])}")
    except Exception as exc:
        print(f"[inbound-reconcile] failed type={type(exc).__name__}")
    finally:
        release_job_lock("inbound_event_reconcile")
