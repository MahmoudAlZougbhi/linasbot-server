"""Inbound event ledger types and snapshot sanitization."""

from __future__ import annotations

import hashlib
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

EventKind = Literal["meta_dm", "meta_comment"]
EventState = Literal[
    "accepted",
    "queued",
    "processing",
    "completed",
    "failed",
    "dead_letter",
]

TERMINAL_STATES = frozenset({"completed", "dead_letter"})
ACTIVE_STATES = frozenset({"accepted", "queued", "processing", "failed"})
SAFE_META_SETTINGS_SNAPSHOT_KEYS = frozenset(
    {
        "enabled",
        "page_id",
        "instagram_account_id",
        "graph_api_version",
        "app_id",
        "app_key",
        "tenant_id",
        "binding_id",
        "auth_flow",
        "graph_base_url",
        "instagram_login_user_id",
    }
)


class InboundEventStoreUnavailableError(RuntimeError):
    """Raised when the configured shared ledger cannot be read safely."""


class InboundEventStateTransitionError(RuntimeError):
    """Raised when an authoritative inbound state cannot be proven."""


def sanitize_meta_settings_snapshot(data: object) -> dict[str, Any]:
    """Retain non-secret routing metadata and drop all other snapshot fields."""

    raw = data if isinstance(data, dict) else {}
    return {
        str(key): value
        for key, value in raw.items()
        if str(key) in SAFE_META_SETTINGS_SNAPSHOT_KEYS
        and (isinstance(value, (str, bool, int, float)) or value is None)
    }


@dataclass
class InboundEventRecord:
    event_id: str
    kind: EventKind
    tenant_id: str
    claim_namespace: str
    claim_key: str
    state: EventState
    created_at: float
    updated_at: float
    payload: dict[str, Any] = field(default_factory=dict)
    settings_snapshot: dict[str, Any] = field(default_factory=dict)
    binding_snapshot: dict[str, Any] = field(default_factory=dict)
    conversation_key: str = ""
    queue_job_id: str | None = None
    attempts: int = 0
    last_error: str | None = None
    outbound_status: str | None = None
    ai_output_persisted: bool = False
    revision: int = 0

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["settings_snapshot"] = sanitize_meta_settings_snapshot(self.settings_snapshot)
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InboundEventRecord:
        return cls(
            event_id=str(data["event_id"]),
            kind=str(data.get("kind") or "meta_dm"),  # type: ignore[arg-type]
            tenant_id=str(data.get("tenant_id") or ""),
            claim_namespace=str(data.get("claim_namespace") or ""),
            claim_key=str(data.get("claim_key") or ""),
            state=str(data.get("state") or "accepted"),  # type: ignore[arg-type]
            created_at=float(data.get("created_at") or time.time()),
            updated_at=float(data.get("updated_at") or time.time()),
            payload=dict(data.get("payload") or {}),
            settings_snapshot=sanitize_meta_settings_snapshot(data.get("settings_snapshot")),
            binding_snapshot=dict(data.get("binding_snapshot") or {}),
            conversation_key=str(data.get("conversation_key") or ""),
            queue_job_id=data.get("queue_job_id"),
            attempts=int(data.get("attempts") or 0),
            last_error=data.get("last_error"),
            outbound_status=data.get("outbound_status"),
            ai_output_persisted=bool(data.get("ai_output_persisted")),
            revision=int(data.get("revision") or 0),
        )


def stable_event_id(kind: str, claim_key: str) -> str:
    digest = hashlib.sha256(f"{kind}\0{claim_key}".encode()).hexdigest()
    return f"ibe_{digest[:40]}"
