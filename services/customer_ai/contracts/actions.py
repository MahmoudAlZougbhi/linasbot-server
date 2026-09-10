"""Action proposals and server-authored receipts."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from services.customer_ai.budgets import SCHEMA_VERSION
from services.customer_ai.contracts.enums import ActionState, ActionType


class ActionProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str
    action_type: ActionType
    target_id: str = ""
    fields: dict[str, Any] = Field(default_factory=dict)
    expected_revision: str = ""
    depends_on: list[str] = Field(default_factory=list)
    confirmation_message_id: str = ""
    destination: str = ""


class ActionProposalSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    actions: list[ActionProposal] = Field(default_factory=list)


class ActionReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_id: str
    action_type: ActionType
    state: ActionState
    backend_id: str = ""
    revision: str = ""
    reason: str = ""
    idempotency_key: str = ""


class ActionReceiptSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    receipts: list[ActionReceipt] = Field(default_factory=list)
