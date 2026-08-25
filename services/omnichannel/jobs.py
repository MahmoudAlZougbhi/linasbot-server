"""Queue jobs: AI generation and provider delivery are separate."""

from __future__ import annotations

from typing import Any

from services.queues.models import QueueJob


async def handle_omni_generate(job: QueueJob) -> dict[str, Any]:
    from services.omnichannel.generate import handle_omnichannel_generate

    return await handle_omnichannel_generate(job)


async def handle_omni_deliver(job: QueueJob) -> dict[str, Any]:
    from services.omnichannel.deliver import handle_omnichannel_deliver

    return await handle_omnichannel_deliver(job)


async def handle_whatsapp_generate(job: QueueJob) -> dict[str, Any]:
    from services.whatsapp_cloud.ai_bridge import maybe_generate_and_send_ai_reply

    snapshot = dict(job.payload or {})
    snapshot.pop("_conversation_key", None)
    snapshot.pop("_provider", None)
    snapshot.pop("_logical_queue", None)
    await maybe_generate_and_send_ai_reply(snapshot)
    return {"ok": True, "channel": "whatsapp"}


async def handle_whatsapp_deliver_retry(job: QueueJob) -> dict[str, Any]:
    from services.whatsapp_cloud.delivery_retry import retry_pending_outbound_intents

    return await retry_pending_outbound_intents(tenant_id=job.tenant_id)


async def handle_whatsapp_intent_deliver(job: QueueJob) -> dict[str, Any]:
    from services.whatsapp_cloud.delivery_retry import send_canonical_intent

    return await send_canonical_intent(str((job.payload or {}).get("intent_id") or ""))


async def handle_web_chat_generate(job: QueueJob) -> dict[str, Any]:
    from services.web_chat.generate_job import process_web_chat_generation_job

    return await process_web_chat_generation_job(job.payload or {})


async def handle_tiktok_webhook_event(job: QueueJob) -> dict[str, Any]:
    from services.tiktok_business.webhook_jobs import process_claimed_webhook

    return await process_claimed_webhook(job.payload or {})


async def handle_operator_deliver(job: QueueJob) -> dict[str, Any]:
    from services.omnichannel.delivery_dispatch import deliver_outbox_row

    return await deliver_outbox_row(job)
