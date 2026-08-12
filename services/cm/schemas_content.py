"""CM content/policy Pydantic models (LOC split from schemas).

Re-exported by services.cm.schemas — import from schemas for public API.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from services.cm.constants import (
    RESPONSE_LANGUAGE_MAP,
    SUPPORTED_LANGUAGES,
)

LangCode = Literal["ar", "en", "fr", "franco"]
Audience = Literal["men", "women", "general"]
GenderAudience = Literal["male", "female", "any"]
ValidationSeverity = Literal["error", "warning"]


class CmBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class LocalizedLabels(CmBaseModel):
    """Display labels. Franco is optional; FAQ still owns 4-lang auto-translate."""

    en: str = ""
    ar: str = ""
    fr: str = ""
    franco: str = ""


class AiBasics(CmBaseModel):
    assistant_name: str = ""
    clinic_name: str = ""  # Generic business display name (legacy field key retained).
    ai_role: str = ""
    business_purpose: str = ""
    short_introduction: str = ""
    greeting_behavior: str = ""
    identity_summary: str = ""
    advanced_instructions: str = ""
    notes: str | None = None


class LanguagePolicy(CmBaseModel):
    supported_languages: tuple[str, ...] = Field(default_factory=lambda: SUPPORTED_LANGUAGES)
    # Product-fixed map (EN→EN, AR→AR, FR→FR, Franco→AR). Tenant payloads are coerced.
    response_language_map: dict[str, str] = Field(default_factory=lambda: dict(RESPONSE_LANGUAGE_MAP))
    default_language: str = "ar"
    mixed_language_behavior: str = ""
    unknown_language_behavior: str = ""
    notes: str | None = None

    @field_validator("supported_languages")
    @classmethod
    def _validate_supported(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        allowed = set(SUPPORTED_LANGUAGES)
        unknown = [lang for lang in value if lang not in allowed]
        if unknown:
            raise ValueError(f"unsupported languages: {unknown}")
        return value

    @field_validator("response_language_map", mode="before")
    @classmethod
    def _freeze_response_language_map(cls, _value: object) -> dict[str, str]:
        """Ignore tenant edits — reply map is system-fixed (sabtin)."""
        return dict(RESPONSE_LANGUAGE_MAP)


class StylePolicy(CmBaseModel):
    tone: str = ""
    formality: str = ""
    response_length: str = ""
    emoji_level: str = ""
    one_question_at_a_time: bool = True
    use_customer_name: bool = False
    preferred_terms: list[str] = Field(default_factory=list)
    example_replies: list[str] = Field(default_factory=list)
    do_list: list[str] = Field(default_factory=list)
    dont_list: list[str] = Field(default_factory=list)
    style_body: str = ""
    notes: str | None = None


class ServiceRecord(CmBaseModel):
    id: str
    labels: LocalizedLabels = Field(default_factory=LocalizedLabels)
    available: bool = True
    category: str | None = None
    aliases: list[str] = Field(default_factory=list)
    audience: Audience = "general"
    notes: str | None = None


class BranchHours(CmBaseModel):
    monday: str = ""
    tuesday: str = ""
    wednesday: str = ""
    thursday: str = ""
    friday: str = ""
    saturday: str = ""
    sunday: str = ""
    summary: str = ""


class BranchRecord(CmBaseModel):
    id: str
    labels: LocalizedLabels = Field(default_factory=LocalizedLabels)
    address: str = ""  # Legacy / composed display line used by answer facts.
    street: str = ""
    building: str = ""
    floor: str = ""
    country: str = ""
    maps_url: str = ""
    hours: BranchHours = Field(default_factory=BranchHours)
    available: bool = True
    notes: str | None = None

    def composed_address(self) -> str:
        """Prefer structured parts when present; fall back to legacy address."""
        parts = [p.strip() for p in (self.street, self.building, self.floor, self.country) if p and p.strip()]
        if parts:
            return ", ".join(parts)
        return (self.address or "").strip()


class PriceRecord(CmBaseModel):
    """Legacy structured price row (service_id keyed). Prefer PriceEntry + CatalogItem."""

    id: str
    service_id: str
    amount: float
    currency: str = "USD"
    unit: str | None = None
    branch_id: str | None = None
    notes: str | None = None

    @field_validator("amount")
    @classmethod
    def _non_negative(cls, value: float) -> float:
        if value < 0:
            raise ValueError("amount must be >= 0")
        return value


class ArticleAttachment(CmBaseModel):
    """Case/example media on a knowledge or care article (bytes live in CM media store).

    ``caption`` tells the AI when this image/file applies (e.g. filled form vs blank template).
    """

    id: str
    kind: Literal["image", "file"] = "file"
    caption: str = ""
    mime: str = ""
    filename: str = ""
    size: int = Field(default=0, ge=0)


class ArticleRecord(CmBaseModel):
    id: str
    title: str = ""
    body: str = ""
    tags: list[str] = Field(default_factory=list)
    language: str = ""
    audience: Audience = "general"
    category: str = ""
    status: Literal["draft", "active", "archived", "restricted"] = "active"
    source_filename: str | None = None
    source_checksum: str | None = None
    linked_service_ids: list[str] = Field(default_factory=list)
    linked_branch_ids: list[str] = Field(default_factory=list)
    notes: str | None = None
    attachments: list[ArticleAttachment] = Field(default_factory=list)


class HandoffContact(CmBaseModel):
    """Structured human-contact destination (phone / WhatsApp / email / URL)."""

    id: str
    destination_type: Literal["phone", "whatsapp", "email", "url"] = "whatsapp"
    destination_value: str = ""
    # Legacy field retained for older drafts; used when destination_value is empty.
    phone_e164: str = ""
    label: str = ""
    branch_id: str | None = None
    gender: GenderAudience = "any"
    topic_id: str | None = None
    notes: str | None = None

    def resolved_destination(self) -> tuple[str, str]:
        """Return (type, value) preferring destination_* then legacy phone_e164."""
        value = (self.destination_value or "").strip() or (self.phone_e164 or "").strip()
        dtype = (self.destination_type or "whatsapp").strip().lower()
        if not value:
            return dtype, ""
        if not (self.destination_value or "").strip() and (self.phone_e164 or "").strip():
            return "whatsapp", value
        return dtype, value


class HandoffMatrixRow(CmBaseModel):
    id: str
    contact_id: str
    service_id: str | None = None
    topic_id: str | None = None
    branch_id: str | None = None
    gender: GenderAudience = "any"
    enabled: bool = True
    notes: str | None = None


class HandoffPolicy(CmBaseModel):
    contacts: list[HandoffContact] = Field(default_factory=list)
    matrix: list[HandoffMatrixRow] = Field(default_factory=list)
    policy_text: str = ""
    notes: str | None = None


class RestrictedTopic(CmBaseModel):
    id: str
    labels: LocalizedLabels = Field(default_factory=LocalizedLabels)
    keywords: list[str] = Field(default_factory=list)
    active: bool = True
    refuse_template: str = ""
    notes: str | None = None


class RestrictedPolicy(CmBaseModel):
    topics: list[RestrictedTopic] = Field(default_factory=list)
    notes: str | None = None


class ActionCapability(CmBaseModel):
    id: str
    enabled: bool = False
    notes: str | None = None


class ActionsSection(CmBaseModel):
    """Tenant-enabled capabilities. Code defines how; tenant chooses which."""

    items: list[ActionCapability] = Field(
        default_factory=lambda: [
            ActionCapability(id="respond_facebook_dm", enabled=True),
            ActionCapability(id="respond_instagram_dm", enabled=True),
            ActionCapability(id="respond_facebook_comments", enabled=False),
            ActionCapability(id="respond_instagram_comments", enabled=False),
            ActionCapability(id="human_handoff", enabled=True),
            ActionCapability(id="photo_analysis", enabled=False),
        ]
    )
    notes: str | None = None


class CommentRule(CmBaseModel):
    """Structured comment behavior: match customer text → public reply, DM, or ignore.

    Optional ``post_id`` targets a Meta post/media id when known. Full Meta post picker
    is a follow-up; owners can paste ids today.
    """

    id: str
    enabled: bool = True
    name: str = ""
    match_mode: Literal["contains", "any_keyword", "regex"] = "any_keyword"
    keywords: list[str] = Field(default_factory=list)
    pattern: str = ""
    post_id: str = ""
    channel: Literal["any", "facebook", "instagram"] = "any"
    action: Literal["reply_comment", "reply_dm", "ignore"] = "reply_comment"
    reply_template: str = ""
    notes: str | None = None


class CommentsSection(CmBaseModel):
    """Comment-specific CM policy evaluated by the Meta comment runtime before AI reply."""

    default_action: Literal["reply_comment", "ignore"] = "reply_comment"
    policy_text: str = ""
    rules: list[CommentRule] = Field(default_factory=list)
    notes: str | None = None
