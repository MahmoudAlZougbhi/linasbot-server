"""Typed stream events, cards, and choices for Owner Copilot V2."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

StreamEventType = Literal[
    "thinking",
    "status",
    "delta",
    "card",
    "choices",
    "title_updated",
    "error",
    "done",
    "cancelled",
]

CardKind = Literal[
    "proposal",
    "diagnosis",
    "progress",
    "success",
    "failure",
    "price_list_import",
    "setup",
    "activity",
]


@dataclass
class StreamEvent:
    type: StreamEventType
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, **self.payload}


@dataclass
class ChatCard:
    id: str
    kind: CardKind
    title: str
    body: str = ""
    status: str = "active"
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ChatChoice:
    id: str
    label: str
    action: str
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class OwnerV2TurnResult:
    reply_text: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    cards: list[dict[str, Any]] = field(default_factory=list)
    choices: list[dict[str, Any]] = field(default_factory=list)
    pending_confirmation: str | None = None
    proposed_patch: dict[str, Any] | None = None
    route: dict[str, Any] | None = None
    context_tokens: int = 0
    setup_stage: str | None = None
    quick_actions: list[dict[str, str]] = field(default_factory=list)
    model: str | None = None
    cancelled: bool = False
    creative_draft: dict[str, Any] | None = None  # always None in V2

    def to_legacy_owner_turn(self) -> dict[str, Any]:
        """Shape compatible with modules/owner_ai_api non-stream response."""
        return {
            "reply_text": self.reply_text,
            "tool_calls": self.tool_calls,
            "pending_confirmation": self.pending_confirmation,
            "proposed_patch": self.proposed_patch,
            "creative_draft": None,
            "route": self.route,
            "context_tokens": self.context_tokens,
            "setup_stage": self.setup_stage,
            "quick_actions": self.quick_actions,
            "cards": self.cards,
            "choices": self.choices,
            "model": self.model,
        }
