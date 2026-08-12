"""Pydantic schemas for Customer Requests APIs."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RequestCreateBody(BaseModel):
    """AI-tool / internal create after customer confirmation."""

    request_type: str
    source_channel: str
    customer_confirmed: bool = False
    idempotency_key: str = Field(min_length=8, max_length=128)
    source_account_id: str | None = None
    external_customer_id: str | None = None
    platform_username: str | None = None
    customer_display_name: str | None = None
    customer_name: str | None = None
    phone_normalized: str | None = None
    email: str | None = None
    conversation_id: str | None = None
    originating_message_id: str | None = None
    originating_comment_id: str | None = None
    title: str | None = None
    collected_fields: dict[str, Any] | None = None
    requested_items: list[Any] | dict[str, Any] | None = None
    requested_branch: str | None = None
    preferred_date: str | None = None
    preferred_time: str | None = None
    fulfillment_preference: str | None = None
    delivery_address: str | None = None
    customer_notes: str | None = None
    configuration_version: str | None = None


class RequestAssignBody(BaseModel):
    assigned_user_id: str | None = None
    row_version: int


class RequestNoteBody(BaseModel):
    body: str = Field(min_length=1, max_length=8000)


class RequestStatusBody(BaseModel):
    to_status: str
    row_version: int
    cancellation_reason: str | None = None


class RequestFinalActionBody(BaseModel):
    action: str
    row_version: int
    completion_message: str | None = None
    idempotency_key: str = Field(min_length=8, max_length=128)
    send_notification: bool = True


class RequestNotifyRetryBody(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=128)


class RequestListQuery(BaseModel):
    request_type: str | None = None
    status: str | None = None
    source_channel: str | None = None
    assigned_user_id: str | None = None
    q: str | None = None
    cursor: str | None = None
    limit: int = Field(default=25, ge=1, le=100)
