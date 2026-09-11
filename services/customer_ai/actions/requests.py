"""Persist service/product requests through the real Requests backend."""

from __future__ import annotations

from typing import Any

from services.customer_ai.actions.confirm import confirmation_valid
from services.customer_ai.actions.request_fields import merge_fields_for_persist
from services.customer_ai.contracts.actions import ActionProposal, ActionReceipt
from services.requests.capture import normalize_source_channel
from services.requests.config_loader import published_configuration_version
from services.requests.schemas import RequestCreateBody
from services.requests.service import CustomerRequestsError, CustomerRequestsService


def request_source_channel(raw: str) -> str | None:
    """Map a Brain channel onto a Requests source. Unknown stays unknown."""
    return normalize_source_channel(raw)


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
    source = request_source_channel(channel)
    if not source:
        return ActionReceipt(
            action_id=f"req:{proposal.task_id}",
            action_type=proposal.action_type,
            state="rejected",
            reason="invalid_source_channel",
        )
    body = RequestCreateBody(
        request_type=request_type,
        source_channel=source,
        customer_confirmed=True,
        idempotency_key=str(fields.get("idempotency_key") or f"{tenant_id}:{conversation_id}:{proposal.task_id}")[:128],
        external_customer_id=customer_id or None,
        conversation_id=conversation_id or None,
        originating_message_id=message_id or None,
        title=str(fields.get("title") or proposal.target_id or request_type),
        collected_fields=merge_fields_for_persist(
            tenant_id,
            request_type,
            fields.get("collected_fields") if isinstance(fields.get("collected_fields"), dict) else {},
        ),
        requested_items=fields.get("requested_items"),
        requested_branch=str(fields.get("branch") or "") or None,
        configuration_version=published_configuration_version(tenant_id),
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
        backend_id=str(created.get("request_id") or created.get("id") or ""),
        revision=str(created.get("row_version") or created.get("request_number") or ""),
        idempotency_key=body.idempotency_key,
    )
