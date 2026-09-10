"""Persist service/product requests through the real Requests backend."""

from __future__ import annotations

from typing import Any

from services.customer_ai.contracts.actions import ActionProposal, ActionReceipt
from services.customer_ai.actions.confirm import confirmation_valid
from services.requests.schemas import RequestCreateBody
from services.requests.service import CustomerRequestsError, CustomerRequestsService


def _channel(raw: str) -> str:
    text = (raw or "").strip().lower()
    if text in {"instagram_dm", "facebook_messenger", "whatsapp_cloud", "comment_linked_dm"}:
        return text
    if "whatsapp" in text:
        return "whatsapp_cloud"
    if "facebook" in text:
        return "facebook_messenger"
    if "comment" in text:
        return "comment_linked_dm"
    return "instagram_dm"


def persist_request(
    *,
    session: Any,
    tenant_id: str,
    proposal: ActionProposal,
    channel: str,
    customer_id: str,
    conversation_id: str,
    message_id: str,
    customer_text: str,
    current_revision: str,
) -> ActionReceipt:
    fields = proposal.fields
    if not confirmation_valid(
        message_id=proposal.confirmation_message_id or message_id,
        customer_text=str(fields.get("confirmation_text") or customer_text),
        expected_revision=proposal.expected_revision,
        current_revision=current_revision,
    ):
        return ActionReceipt(
            action_id=f"req:{proposal.task_id}",
            action_type=proposal.action_type,
            state="rejected",
            reason="confirmation_required",
        )
    request_type = str(fields.get("request_type") or "APPOINTMENT").upper()
    if request_type not in {"ORDER", "APPOINTMENT", "OTHER"}:
        return ActionReceipt(
            action_id=f"req:{proposal.task_id}",
            action_type=proposal.action_type,
            state="rejected",
            reason="invalid_request_type",
        )
    body = RequestCreateBody(
        request_type=request_type,
        source_channel=_channel(channel),
        customer_confirmed=True,
        idempotency_key=str(fields.get("idempotency_key") or f"{tenant_id}:{conversation_id}:{proposal.task_id}")[:128],
        external_customer_id=customer_id or None,
        conversation_id=conversation_id or None,
        originating_message_id=message_id or None,
        title=str(fields.get("title") or proposal.target_id or request_type),
        collected_fields=dict(fields.get("collected_fields") or {}),
        requested_items=fields.get("requested_items"),
        requested_branch=str(fields.get("branch") or "") or None,
        configuration_version=current_revision or None,
    )
    try:
        created = CustomerRequestsService(session).create_from_ai(tenant_id=tenant_id, body=body)
    except CustomerRequestsError as exc:
        return ActionReceipt(
            action_id=f"req:{proposal.task_id}",
            action_type=proposal.action_type,
            state="failure",
            reason=exc.code,
        )
    return ActionReceipt(
        action_id=f"req:{proposal.task_id}",
        action_type=proposal.action_type,
        state="success",
        backend_id=str(created.get("id") or ""),
        revision=str(created.get("row_version") or created.get("request_number") or ""),
        idempotency_key=body.idempotency_key,
    )
