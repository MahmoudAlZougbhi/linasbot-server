"""Reconcile WhatsApp retryable outbound intents."""

from __future__ import annotations


async def run_whatsapp_outbound_retry_job() -> None:
    from services.integrations.whatsapp.delivery_retry import retry_pending_outbound_intents
    from services.scale.job_interval_lock import job_interval_lock

    with job_interval_lock("whatsapp_outbound_retry", ttl_seconds=50) as acquired:
        if not acquired:
            return
        await retry_pending_outbound_intents()
