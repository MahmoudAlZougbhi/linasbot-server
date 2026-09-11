"""CustomerTurn — trusted identity is server-authored."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from services.customer_ai.budgets import SCHEMA_VERSION
from services.customer_ai.contracts.enums import InvocationKind, Surface


class VisibleMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    role: str
    text: str = ""
    timestamp: str = ""
    visible_to_customer: bool = True
    is_current_inbound: bool = False


class HistorySnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    messages: list[VisibleMessage] = Field(default_factory=list)
    high_water_mark: str = ""
    included_inbound_ids: list[str] = Field(default_factory=list)
    truncated_to_cap: bool = False
    overflow: bool = False


class MediaView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attachment_types: list[str] = Field(default_factory=list)
    transcript: str = ""
    extract_preview: str = ""
    inbound_link: str = ""
    image_media_id: str = ""
    safety_blocked: bool = False


class ConversationState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    discussed_entity_ids: list[str] = Field(default_factory=list)
    branch_id: str = ""
    active_draft_id: str = ""
    confirmed_fields: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    greeted: bool = False
    control_epoch: int = 0
    handoff_active: bool = False
    draft_revision: str = ""


class SourceVersions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cm_publication: str = ""
    products_revision: str = ""
    faq_revision: str = ""
    index_space_ids: list[str] = Field(default_factory=list)
    prompt_version: str = SCHEMA_VERSION
    model_ids: dict[str, str] = Field(default_factory=dict)


class CustomerTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    tenant_id: str
    customer_id: str = ""
    conversation_id: str = ""
    channel: str = ""
    account_id: str = ""
    surface: Surface = "dm"
    invocation_kind: InvocationKind = "dm"
    event_ids: list[str] = Field(default_factory=list)
    history: HistorySnapshot = Field(default_factory=HistorySnapshot)
    control_epoch: int = 0
    versions: SourceVersions = Field(default_factory=SourceVersions)
    media: MediaView = Field(default_factory=MediaView)
    state: ConversationState = Field(default_factory=ConversationState)
    followup_goal: str = ""
    extra: dict[str, Any] = Field(default_factory=dict)
