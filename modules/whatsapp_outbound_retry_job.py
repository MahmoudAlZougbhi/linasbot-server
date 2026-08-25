"""Reconcile WhatsApp retryable outbound intents."""

from __future__ import annotations


async def run_whatsapp_outbound_retry_job() -> None:
    from services.durable_event_claim import release_job_lock, try_acquire_job_lock
    from services.whatsapp_cloud.delivery_retry import retry_pending_outbound_intents

    if not try_acquire_job_lock("whatsapp_outbound_retry", ttl_seconds=55):
        return
    try:
        await retry_pending_outbound_intents()
    finally:
        release_job_lock("whatsapp_outbound_retry")
