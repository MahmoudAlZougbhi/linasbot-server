"""Shared Web Chat store datatypes."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class WebChatMessage:
    id: str
    role: str
    content: str
    created_at: float


@dataclass
class WebChatVisitorSession:
    id: str
    tenant_id: str
    widget_key: str
    created_at: float
    updated_at: float
    authority_hash: str = ""
    messages: list[WebChatMessage] = field(default_factory=list)
    pending_assistant: list[WebChatMessage] = field(default_factory=list)
