"""Fail-closed inbound accept: persist then durable enqueue, else raise for provider retry."""

from __future__ import annotations

from db.session import whatsapp_session
from services.omnichannel.contract import NormalizedInbound
from services.omnichannel.metrics import incr
from services.omnichannel.queues import logical_for_channel
from services.omnichannel.store import accept_inbound


class InboundAcceptError(RuntimeError):
    """Provider must retry; we did not acknowledge the event."""


def enqueue_generate_job(
    *,
    inbound_id: str,
    tenant_id: str,
    channel: str,
    surface: str,
    conversation_key: str,
) -> str:
    from services.omnichannel.enqueue import AMBIGUOUS_ENQUEUE, enqueue_job

    logical = logical_for_channel(channel=channel, surface=surface)
    job_id = enqueue_job(
        logical_queue=logical,
        job_type="omni_generate",
        tenant_id=tenant_id,
        payload={
            "inbound_id": inbound_id,
            "channel": channel,
            "surface": surface,
            "_priority": "customer_conversation",
            "_queue_class": logical,
        },
        idempotency_key=f"omni_gen:{inbound_id}",
        conversation_key=conversation_key,
        provider="openai",
    )
    if not job_id or job_id == AMBIGUOUS_ENQUEUE:
        raise InboundAcceptError("durable_enqueue_failed")
    return job_id


def accept_and_enqueue(event: NormalizedInbound) -> tuple[str, bool]:
    with whatsapp_session(require=True) as session:
        row, created = accept_inbound(session, event)
        inbound_id = row.id
        if not created:
            session.commit()
            incr("inbound_duplicate")
            return inbound_id, False
        try:
            job_id = enqueue_generate_job(
                inbound_id=inbound_id,
                tenant_id=event.tenant_id,
                channel=event.channel,
                surface=event.surface,
                conversation_key=event.conversation_key,
            )
        except Exception as exc:
            from db.models.omnichannel import OmnichannelInboundEvent

            stuck = session.get(OmnichannelInboundEvent, inbound_id)
            if stuck is not None and stuck.state == "accepted":
                session.delete(stuck)
            session.commit()
            incr("inbound_enqueue_failed")
            raise InboundAcceptError("durable_enqueue_failed") from exc
        row.state = "queued"
        row.queue_job_id = job_id
        session.commit()
        incr("inbound_accepted")
        return inbound_id, True


def enqueue_deliver_job(*, outbox_id: str, tenant_id: str, channel: str, surface: str, conversation_key: str) -> str:
    from services.omnichannel.enqueue import AMBIGUOUS_ENQUEUE, enqueue_job
    from services.omnichannel.queues import outbound_logical

    logical = outbound_logical(channel=channel, surface=surface)
    job_id = enqueue_job(
        logical_queue=logical,
        job_type="omni_deliver",
        tenant_id=tenant_id,
        payload={
            "outbox_id": outbox_id,
            "channel": channel,
            "surface": surface,
            "_priority": "customer_conversation",
            "_queue_class": logical,
        },
        idempotency_key=f"omni_del:{outbox_id}",
        conversation_key=conversation_key,
        provider=channel if channel != "web_chat" else "openai",
    )
    if not job_id or job_id == AMBIGUOUS_ENQUEUE:
        raise InboundAcceptError("durable_deliver_enqueue_failed")
    return job_id
