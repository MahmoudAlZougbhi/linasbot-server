"""EvidenceBundle — typed, source-backed, never raw search dumps."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from services.customer_ai.budgets import SCHEMA_VERSION
from services.customer_ai.contracts.enums import RetrievalOutcome, SourceFamily


class EvidenceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    source_family: SourceFamily
    source_id: str
    revision: str = ""
    authority: str = "canonical"
    title: str = ""
    text: str = ""
    asset_ids: list[str] = Field(default_factory=list)
    task_ids: list[str] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)


class EvidenceBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    items: list[EvidenceItem] = Field(default_factory=list)
    outcome: RetrievalOutcome = "not_found"
    ambiguities: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
