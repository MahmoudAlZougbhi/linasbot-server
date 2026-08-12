"""Serialize CustomerRequest rows for API responses."""

from __future__ import annotations

from typing import Any

from db.models.requests import CustomerRequest
from db.models.requests_support import CustomerRequestEvent, CustomerRequestNote


def _dt(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return value.isoformat()
    except Exception:
        return str(value)


def serialize_request(
    row: CustomerRequest,
    *,
    include_sensitive: bool = False,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "request_id": row.id,
        "tenant_id": row.tenant_id,
        "request_number": row.request_number,
        "request_type": row.request_type,
        "status": row.status,
        "source_channel": row.source_channel,
        "source_account_id": row.source_account_id,
        "external_customer_id": row.external_customer_id,
        "platform_username": row.platform_username,
        "customer_display_name": row.customer_display_name,
        "customer_name": row.customer_name,
        "conversation_id": row.conversation_id,
        "originating_message_id": row.originating_message_id,
        "originating_comment_id": row.originating_comment_id,
        "title": row.title,
        "collected_fields": row.collected_fields,
        "requested_items": row.requested_items,
        "requested_branch": row.requested_branch,
        "preferred_date": row.preferred_date,
        "preferred_time": row.preferred_time,
        "fulfillment_preference": row.fulfillment_preference,
        "customer_notes": row.customer_notes,
        "assigned_user_id": row.assigned_user_id,
        "configuration_version": row.configuration_version,
        "row_version": row.row_version,
        "notification_status": row.notification_status,
        "last_notification_error": row.last_notification_error,
        "completion_message": row.completion_message,
        "cancellation_reason": row.cancellation_reason,
        "created_at": _dt(row.created_at),
        "submitted_at": _dt(row.submitted_at),
        "updated_at": _dt(row.updated_at),
        "confirmed_at": _dt(row.confirmed_at),
        "ready_at": _dt(row.ready_at),
        "completed_at": _dt(row.completed_at),
        "cancelled_at": _dt(row.cancelled_at),
    }
    if include_sensitive:
        data["phone_normalized"] = row.phone_normalized
        data["email"] = row.email
        data["delivery_address"] = row.delivery_address
    else:
        data["phone_present"] = bool(row.phone_normalized)
        data["email_present"] = bool(row.email)
        data["delivery_address_present"] = bool(row.delivery_address)
    return data


def serialize_card(row: CustomerRequest) -> dict[str, Any]:
    """List card — no full phone/address."""
    return {
        "request_id": row.id,
        "request_number": row.request_number,
        "request_type": row.request_type,
        "status": row.status,
        "source_channel": row.source_channel,
        "customer_display_name": row.customer_display_name or row.customer_name,
        "platform_username": row.platform_username,
        "title": row.title,
        "preferred_date": row.preferred_date,
        "preferred_time": row.preferred_time,
        "assigned_user_id": row.assigned_user_id,
        "notification_status": row.notification_status,
        "created_at": _dt(row.created_at),
        "row_version": row.row_version,
    }


def serialize_event(ev: CustomerRequestEvent) -> dict[str, Any]:
    return {
        "id": ev.id,
        "event_type": ev.event_type,
        "actor_kind": ev.actor_kind,
        "actor_user_id": ev.actor_user_id,
        "payload": ev.payload,
        "created_at": _dt(ev.created_at),
    }


def serialize_note(note: CustomerRequestNote) -> dict[str, Any]:
    return {
        "id": note.id,
        "author_user_id": note.author_user_id,
        "body": note.body,
        "created_at": _dt(note.created_at),
    }
