"""PlannerPlan — untrusted until validated against the original message."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from services.customer_ai.budgets import SCHEMA_VERSION
from services.customer_ai.contracts.enums import SourceFamily, TaskType


class TaskSpan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message_id: str = ""
    start: int = 0
    end: int = 0
    text: str = ""


class PlannerTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    type: TaskType
    span: TaskSpan = Field(default_factory=TaskSpan)
    entity_mentions: list[str] = Field(default_factory=list)
    resolved_entity_ids: list[str] = Field(default_factory=list)
    source_families: list[SourceFamily] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    policy_notes: list[str] = Field(default_factory=list)


class PlannerPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    tasks: list[PlannerTask] = Field(default_factory=list)
    read_only: bool = True
