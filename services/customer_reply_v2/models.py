"""Typed models for Customer Reply AI V2."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

EvidenceStatus = Literal["sufficient", "insufficient_can_retry", "insufficient_final", "faq_hit", "policy_stop"]
ChannelKind = Literal[
    "instagram_dm",
    "facebook_dm",
    "instagram_comment",
    "facebook_comment",
    "whatsapp_dm",
]


@dataclass
class CustomerFacts:
    tenant_id: str
    channel: str
    asset_id: str
    provider_sender_id: str
    provider_display_name: str = ""
    customer_confirmed_name: str | None = None
    name_source: Literal["provider", "explicit_self_report"] = "provider"
    gender: str | None = None  # only when explicitly stated
    preferred_language: str | None = None

    @property
    def effective_name(self) -> str:
        if self.customer_confirmed_name and self.name_source == "explicit_self_report":
            return self.customer_confirmed_name
        return self.provider_display_name or ""

    def to_safe_dict(self) -> dict[str, Any]:
        return {
            "effective_name": self.effective_name,
            "name_source": self.name_source,
            "has_confirmed_name": bool(self.customer_confirmed_name),
            "gender": self.gender,
            "preferred_language": self.preferred_language,
            # never expose raw provider sender id in model prompts as a secret; hashed later
        }


@dataclass
class ConversationMessage:
    role: Literal["user", "assistant"]
    content: str
    timestamp: float | None = None


@dataclass
class ConversationWindow:
    messages: list[ConversationMessage]
    window_hours: float
    context_compacted: bool = False
    compacted_summary: str = ""
    excluded_outside_window: int = 0

    def as_openai_messages(self) -> list[dict[str, str]]:
        out: list[dict[str, str]] = []
        if self.context_compacted and self.compacted_summary:
            out.append({"role": "system", "content": f"Earlier conversation summary: {self.compacted_summary}"})
        for msg in self.messages:
            out.append({"role": msg.role, "content": msg.content})
        return out


@dataclass
class ManifestSection:
    section_id: str
    name: str
    description: str
    published_revision: str
    item_count: int
    fixed_answer_context: bool
    selectable: bool


@dataclass
class ItemIndexEntry:
    item_id: str
    section_id: str
    title: str
    short_description: str = ""
    language: str = ""
    status: str = "active"
    relations: dict[str, Any] = field(default_factory=dict)
    published_revision: str = ""
    resource_summary: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvidenceRecord:
    source_id: str
    section_id: str
    title: str
    content: str
    published_revision: str
    allowed_resources: list[dict[str, str]] = field(default_factory=list)


@dataclass
class RetrievalPlan:
    selected_section_ids: list[str] = field(default_factory=list)
    selected_item_ids: list[str] = field(default_factory=list)
    reason_codes: list[str] = field(default_factory=list)
    media_context_required: bool = False
    multi_intent: bool = False
    evidence_status: EvidenceStatus = "insufficient_can_retry"
    missing_information_category: str = ""
    confidence_category: str = "low"
    round_index: int = 1


@dataclass
class RetrievalResult:
    evidence: list[EvidenceRecord]
    evidence_status: EvidenceStatus
    rounds_used: int
    selected_section_ids: list[str] = field(default_factory=list)
    selected_source_ids: list[str] = field(default_factory=list)
    tool_trace: list[dict[str, Any]] = field(default_factory=list)
    requested_model: str = ""
    returned_model: str = ""
    refused_third_round: bool = False
    error: str | None = None
    active_product_id: str | None = None
    requested_reasoning_effort: str | None = None
    effective_reasoning_effort: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    recommended_tera_effort: str | None = None


@dataclass
class AnswerLunaResult:
    reply_text: str
    detected_language: str = ""
    grounding_status: str = "grounded"
    evidence_source_ids: list[str] = field(default_factory=list)
    customer_fact_updates: dict[str, Any] = field(default_factory=dict)
    handoff_intent: str | None = None
    safe_failure_category: str | None = None
    requested_model: str = ""
    returned_model: str = ""
    reasoning_effort: str = "medium"
    requested_reasoning_effort: str | None = None
    effective_reasoning_effort: str | None = None
    stage: str = "answer"
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    raw_structured: dict[str, Any] = field(default_factory=dict)
    media_actions: list[dict[str, Any]] = field(default_factory=list)
    draft_actions: list[dict[str, Any]] = field(default_factory=list)
    request_actions: list[dict[str, Any]] = field(default_factory=list)
    resource_actions: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class CommentMediaContext:
    media_type: str = ""  # image | carousel | video | reel | unknown
    caption: str = ""
    parent_comment: str = ""
    nearby_replies: list[str] = field(default_factory=list)
    image_urls: list[str] = field(default_factory=list)  # bounded remote URLs
    image_inputs: list[dict[str, str]] = field(default_factory=list)  # multimodal {url, kind}
    cached_visual_summary: str = ""
    frame_count: int = 0
    uncertainty_required: bool = False
    media_revision: str = ""
    media_status: str = "unknown"  # available|partial|caption_only|missing|failed|disabled|not_applicable
    permalink: str = ""
    post_id: str = ""
    carousel_truncated: bool = False
    saw_visuals: bool = False


@dataclass
class CustomerReplyOutcome:
    stop: bool
    reply: str | None = None
    reason: str = ""
    evidence_status: EvidenceStatus | str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    shadow_only: bool = False
    error: str | None = None
