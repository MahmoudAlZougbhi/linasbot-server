"""Typed contracts for WhatsApp Cloud coexistence."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

LifecycleStatus = Literal[
    "disconnected",
    "starting",
    "awaiting_meta",
    "provisioning",
    "syncing_history",
    "connected",
    "needs_attention",
    "failed",
    "revoked",
]

ControlState = Literal["AI_ACTIVE", "HUMAN_PAUSED"]
MessageOrigin = Literal["CUSTOMER", "CLOUD_API", "BUSINESS_APP", "HISTORY", "SYSTEM"]
EventKind = Literal[
    "inbound_message",
    "status",
    "smb_message_echoes",
    "history",
    "smb_app_state_sync",
    "template",
    "account_update",
    "phone_quality",
    "unknown",
]
ReturnSurface = Literal["mobile", "web", "bridge"]


@dataclass(frozen=True)
class ConnectionPublicView:
    connection_id: str
    tenant_id: str
    lifecycle_status: LifecycleStatus
    coexistence_mode: str
    connection_source: str
    display_phone_last4: str
    verified_name: str
    waba_id_masked: str
    phone_number_id_masked: str
    webhook_subscription_status: str
    health_status: str
    health_detail: str | None
    ai_eligible: bool
    ai_default_enabled: bool
    history_sync_status: str
    granted_scopes: list[str]
    rollout_blocked_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "connection_id": self.connection_id,
            "tenant_id": self.tenant_id,
            "lifecycle_status": self.lifecycle_status,
            "coexistence_mode": self.coexistence_mode,
            "connection_source": self.connection_source,
            "display_phone_last4": self.display_phone_last4,
            "verified_name": self.verified_name,
            "waba_id_masked": self.waba_id_masked,
            "phone_number_id_masked": self.phone_number_id_masked,
            "webhook_subscription_status": self.webhook_subscription_status,
            "health_status": self.health_status,
            "health_detail": self.health_detail,
            "ai_eligible": self.ai_eligible,
            "ai_default_enabled": self.ai_default_enabled,
            "history_sync_status": self.history_sync_status,
            "granted_scopes": list(self.granted_scopes),
            "rollout_blocked_reason": self.rollout_blocked_reason,
        }


@dataclass(frozen=True)
class ConversationPublicView:
    conversation_id: str
    connection_id: str
    control_state: ControlState
    control_epoch: int
    pause_reason: str | None
    customer_wa_id_masked: str
    customer_profile_name: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "conversation_id": self.conversation_id,
            "connection_id": self.connection_id,
            "control_state": self.control_state,
            "control_epoch": self.control_epoch,
            "pause_reason": self.pause_reason,
            "customer_wa_id_masked": self.customer_wa_id_masked,
            "customer_profile_name": self.customer_profile_name,
        }


@dataclass
class ParsedCloudEvent:
    event_kind: EventKind
    event_key: str
    waba_id: str
    phone_number_id: str
    customer_wa_id: str = ""
    provider_message_id: str = ""
    message_type: str = "text"
    text_body: str = ""
    media_id: str = ""
    media_mime: str = ""
    profile_name: str = ""
    status: str = ""
    raw_change_field: str = ""
    meta: dict[str, Any] = field(default_factory=dict)
