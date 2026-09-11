"""Release unused leftover-credit and Brain holds when generate never reaches send."""

from __future__ import annotations

from typing import Any


def release_unsent_omni_hold(
    *,
    tenant_id: str,
    payload: dict[str, Any] | None = None,
    conversation_key: str = "",
    reservation_id: str | None = None,
    extra_ids: tuple[str, ...] | list[str] = (),
    channel: str = "",
) -> None:
    data = payload if isinstance(payload, dict) else {}
    if reservation_id:
        from services.customer_ai.leftover_reserve import release_leftover_reply

        release_leftover_reply(tenant_id, reservation_id)
    from services.customer_ai.billing import settle_after_send
    from services.customer_ai.history_ids import message_id_for_brain

    inbound = message_id_for_brain(data)
    comment_id = str(data.get("comment_id") or data.get("provider_event_id") or "")
    operation_id = inbound or comment_id or conversation_key
    if not tenant_id or not operation_id:
        return
    settle_after_send(
        tenant_id=tenant_id,
        operation_id=operation_id,
        accepted=False,
        channel=channel or str(data.get("channel") or ""),
        extra_ids=(
            inbound,
            comment_id,
            conversation_key,
            str(data.get("provider_event_id") or ""),
            str(data.get("message_id") or ""),
            *extra_ids,
        ),
    )
