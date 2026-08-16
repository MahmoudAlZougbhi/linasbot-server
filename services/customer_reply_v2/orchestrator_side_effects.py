"""Media + draft side effects after Tera returns structured actions."""

from __future__ import annotations

from typing import Any

from services.customer_reply_v2.draft_actions import plan_drafts_for_turn
from services.customer_reply_v2.media_actions import plan_media_for_turn
from services.customer_reply_v2.resource_actions import plan_resources_for_turn


def plan_turn_side_effects(
    *,
    tenant_id: str,
    customer_id: str,
    conversation_id: str,
    channel: str,
    answer: Any,
    channel_metadata: dict[str, Any] | None,
    meter: Any | None,
    idempotency_key: str,
    allowed_source_ids: list[str] | None = None,
) -> dict[str, Any]:
    media = plan_media_for_turn(
        tenant_id=tenant_id,
        answer=answer,
        channel_metadata=channel_metadata,
        meter=meter,
        idempotency_key=idempotency_key,
    )
    resources = plan_resources_for_turn(
        tenant_id=tenant_id,
        answer=answer,
        channel_metadata=channel_metadata,
        meter=meter,
        idempotency_key=idempotency_key,
        allowed_source_ids=allowed_source_ids,
    )
    drafts = plan_drafts_for_turn(
        tenant_id=tenant_id,
        customer_id=customer_id,
        conversation_id=conversation_id,
        channel=channel,
        answer=answer,
        meter=meter,
        idempotency_key=idempotency_key,
        is_public=bool((channel_metadata or {}).get("is_public")),
    )
    return {**media, **resources, **drafts}
