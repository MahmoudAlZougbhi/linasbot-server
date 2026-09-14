"""Shared types for the customer-reply facade and CM item index."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

ENGINE_REMOVED = "engine_removed"


@dataclass
class ItemIndexEntry:
    item_id: str
    section_id: str
    title: str
    short_description: str = ""
    original_title: str = ""
    ai_search_title: str = ""
    ai_search_description: str = ""
    language: str = ""
    status: str = "active"
    relations: dict[str, Any] = field(default_factory=dict)
    published_revision: str = ""
    resource_summary: dict[str, Any] = field(default_factory=dict)


@dataclass
class CustomerReplyOutcome:
    stop: bool
    reply: str | None = None
    reason: str = ""
    evidence_status: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    shadow_only: bool = False
    error: str | None = None
