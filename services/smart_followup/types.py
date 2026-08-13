"""Shared Smart Follow-Up types."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

SendStatus = Literal["sent", "skipped", "failed", "reconciliation_required"]


@dataclass(frozen=True)
class FollowUpConversationView:
    """Channel-normalized conversation snapshot for eligibility + send."""

    channel: str
    tenant_id: str
    conversation_id: str
    connection_id: str
    control_epoch: int
    control_state: str
    service_window_opens_at: datetime | None
    last_inbound_at: datetime | None
    profile_name: str = ""
    customer_wa_id: str = ""
    user_id: str = ""
    social_sender_id: str = ""
    asset_id: str = ""
    meta_binding_id: str = ""
    meta_app_key: str = ""
    trigger_ref: str = ""


@dataclass(frozen=True)
class FollowUpSendResult:
    status: SendStatus
    reason: str
    provider_message_id: str | None = None
    detail: str | None = None
    reconciliation: bool = False


@dataclass
class FollowUpScheduleRequest:
    tenant_id: str
    channel: str
    connection_id: str
    conversation_id: str
    trigger_ref: str
    control_epoch: int
    trigger_ai_sent_at: datetime | None = None
    channel_context: dict[str, Any] = field(default_factory=dict)
