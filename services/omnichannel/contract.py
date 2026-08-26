"""Normalized inbound/outbound contracts for every customer channel."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Channel = Literal[
    "instagram",
    "facebook",
    "whatsapp",
    "tiktok",
    "web_chat",
]
Surface = Literal["dm", "comment", "web_chat", "operator"]
InboundState = Literal[
    "accepted",
    "queued",
    "generating",
    "reply_ready",
    "rate_limited",
    "sending",
    "delivered",
    "reconciliation_required",
    "failed",
    "dead_letter",
]
OutboundState = Literal[
    "queued",
    "rate_limited",
    "sending",
    "delivered",
    "reconciliation_required",
    "failed",
    "dead_letter",
    "needs_owner_action",
]
DeliveryClass = Literal[
    "success",
    "transient",
    "permanent",
    "ambiguous",
    "permission_blocked",
    "needs_owner_action",
]

INBOUND_TERMINAL = frozenset({"delivered", "dead_letter", "failed"})
OUTBOUND_TERMINAL = frozenset({"delivered", "dead_letter", "needs_owner_action"})
ACTIVE_INBOUND = frozenset(
    {
        "accepted",
        "queued",
        "generating",
        "reply_ready",
        "rate_limited",
        "sending",
        "reconciliation_required",
    }
)


@dataclass(frozen=True)
class NormalizedInbound:
    provider_event_id: str
    tenant_id: str
    account_id: str
    channel: Channel
    surface: Surface
    conversation_key: str
    provider_timestamp: float
    payload_hash: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DeliveryDecision:
    kind: DeliveryClass
    retry_after_seconds: float = 0.0
    http_status: int | None = None
    provider_code: str = ""
    provider_subcode: str = ""
    provider_request_id: str = ""
    reason: str = ""
    retryable: bool = False
