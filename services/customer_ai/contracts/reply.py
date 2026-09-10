"""FinalReplyEnvelope and TurnResult — adapters consume only these."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from services.customer_ai.budgets import SCHEMA_VERSION
from services.customer_ai.contracts.enums import ReplyDecision, StopReason, TaskDisposition


class OutboundMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    destination: str
    text: str = ""
    protected: bool = False
    resource_ids: list[str] = Field(default_factory=list)
    component_id: str = ""


class FinalReplyEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    decision: ReplyDecision = "no_reply"
    messages: list[OutboundMessage] = Field(default_factory=list)
    used_evidence_ids: list[str] = Field(default_factory=list)
    dispositions: dict[str, TaskDisposition] = Field(default_factory=dict)

    @property
    def reply_text(self) -> str:
        for item in self.messages:
            if item.destination in {"dm", "comment", "web_chat"} and item.text.strip():
                return item.text.strip()
        return ""

    @property
    def public_comment_text(self) -> str:
        for item in self.messages:
            if item.destination == "comment":
                return item.text
        return ""

    @property
    def private_dm_text(self) -> str:
        for item in self.messages:
            if item.destination == "dm":
                return item.text
        return ""


class TurnResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    stop_reason: StopReason = "ok"
    envelope: FinalReplyEnvelope = Field(default_factory=FinalReplyEnvelope)
    ai_called: bool = False
    usage: dict[str, Any] = Field(default_factory=dict)
    extra: dict[str, Any] = Field(default_factory=dict)
