"""Pydantic v2 schemas for the Content Management AI Control Plane."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from services.cm.constants import (
    CM_SCHEMA_VERSION,
    INITIAL_RESTRICTED_LABELS,
    INITIAL_RESTRICTED_TOPIC_IDS,
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
    address: str = ""
    hours: BranchHours = Field(default_factory=BranchHours)
    available: bool = True
    notes: str | None = None


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


class AiLimitsSection(CmBaseModel):
    """Tenant-configurable AI usage limits (enforced from published CM)."""

    unlimited: bool = False
    # Capability switches (moved from Settings Features into Content Management).
    voice_processing_enabled: bool = True
    image_analysis_enabled: bool = True
    image_per_day: int = Field(default=20, ge=0)
    image_per_week: int = Field(default=100, ge=0)
    context_lines_per_day: int = Field(default=500, ge=0)
    context_lines_per_week: int = Field(default=2000, ge=0)
    enforce_image_day: bool = True
    enforce_image_week: bool = True
    enforce_context_day: bool = True
    enforce_context_week: bool = True
    notes: str | None = None


class OffDayRule(CmBaseModel):
    id: str
    kind: Literal["weekly", "date", "range"] = "weekly"
    # weekly: 0=Monday .. 6=Sunday
    weekday: int | None = Field(default=None, ge=0, le=6)
    date: str = ""  # YYYY-MM-DD for kind=date
    start_date: str = ""  # YYYY-MM-DD for kind=range
    end_date: str = ""  # YYYY-MM-DD for kind=range
    reason: str = ""
    notes: str | None = None


class OffDaysSection(CmBaseModel):
    timezone: str = "Asia/Beirut"
    rules: list[OffDayRule] = Field(default_factory=list)
    notes: str | None = None


class ServicesSection(CmBaseModel):
    items: list[ServiceRecord] = Field(default_factory=list)
    notes: str | None = None


class BranchesSection(CmBaseModel):
    items: list[BranchRecord] = Field(default_factory=list)
    policy_text: str = ""
    notes: str | None = None


class PricesSection(CmBaseModel):
    """Tenant pricing control plane: catalog + entries + discount rules.

    ``items`` retains legacy PriceRecord rows for backward compatibility; new authoring
    uses ``catalog`` / ``price_entries`` / ``discount_rules`` (business-agnostic).
    """

    categories: list[Any] = Field(default_factory=list)
    catalog: list[Any] = Field(default_factory=list)
    price_entries: list[Any] = Field(default_factory=list)
    discount_rules: list[Any] = Field(default_factory=list)
    dimension_definitions: list[Any] = Field(default_factory=list)
    resources: list[Any] = Field(default_factory=list)
    price_books: list[Any] = Field(default_factory=list)
    rule_sets: list[Any] = Field(default_factory=list)
    package_rules: list[Any] = Field(default_factory=list)
    items: list[PriceRecord] = Field(default_factory=list)
    policy_text: str = ""
    notes: str | None = None


class KnowledgeSection(CmBaseModel):
    items: list[ArticleRecord] = Field(default_factory=list)
    notes: str | None = None


class CareSection(CmBaseModel):
    items: list[ArticleRecord] = Field(default_factory=list)
    notes: str | None = None


class DynamicMessageRecord(CmBaseModel):
    id: str
    name: str = ""
    ar: str = ""
    en: str = ""
    fr: str = ""
    notes: str | None = None


class DynamicMessagesSection(CmBaseModel):
    items: list[DynamicMessageRecord] = Field(default_factory=list)
    notes: str | None = None


class FaqVariant(CmBaseModel):
    language: LangCode
    question: str = ""
    answer: str = ""
    reviewed: bool = False
    is_auto_translated: bool = False


class FaqRecord(CmBaseModel):
    qa_group_id: str
    variants: list[FaqVariant] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    notes: str | None = None
    status: Literal["draft", "active", "archived", "restricted", "needs_review"] = "draft"
    source_language: LangCode | None = None
    reviewed: bool = False
    provenance: str | None = None
    revision: int = 1

    @property
    def is_complete_four_lang(self) -> bool:
        langs = {v.language for v in self.variants if (v.question or "").strip() and (v.answer or "").strip()}
        return langs >= {"ar", "en", "fr", "franco"}


class FaqSection(CmBaseModel):
    items: list[FaqRecord] = Field(default_factory=list)
    notes: str | None = None


class SectionDraftEnvelope(CmBaseModel):
    tenant_id: str
    section: str
    revision: int = Field(ge=0)
    etag: str
    updated_at: datetime
    updated_by: str
    payload: dict[str, object] = Field(default_factory=dict)
    schema_version: int = CM_SCHEMA_VERSION


class EmbeddingPin(CmBaseModel):
    provider: str
    model: str
    version: str
    dimensions: int = Field(gt=0)


class PublishManifest(CmBaseModel):
    tenant_id: str
    content_version_id: str
    index_version_id: str
    created_at: datetime
    created_by: str
    checksums: dict[str, str] = Field(default_factory=dict)
    embedding: EmbeddingPin
    schema_version: int = CM_SCHEMA_VERSION
    notes: str | None = None


class PublishedPointer(CmBaseModel):
    content_version_id: str
    index_version_id: str | None = None
    checksums: dict[str, str] = Field(default_factory=dict)
    embedding_provider: str
    embedding_model: str
    embedding_version: str
    embedding_dimensions: int = Field(gt=0)
    updated_at: datetime | None = None
    schema_version: int = CM_SCHEMA_VERSION


class ValidationFailure(CmBaseModel):
    code: str
    message: str
    path: str | None = None
    severity: ValidationSeverity = "error"
    details: dict[str, str] = Field(default_factory=dict)


class AnswerFact(CmBaseModel):
    kind: str
    value: str
    source_id: str
    path: str | None = None


class AnswerChunk(CmBaseModel):
    source_id: str
    text: str
    score: float | None = None


class AnswerPacket(CmBaseModel):
    tenant_id: str
    content_version_id: str
    index_version_id: str | None = None
    detected_language: str
    response_language: str
    identity: AiBasics = Field(default_factory=AiBasics)
    style: StylePolicy = Field(default_factory=StylePolicy)
    facts: list[AnswerFact] = Field(default_factory=list)
    chunks: list[AnswerChunk] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    platform_rules: list[str] = Field(default_factory=list)
    history_summary: str = ""
    notes: str | None = None


def utc_now() -> datetime:
    return datetime.now(UTC)


def initial_restricted_topics(*, active: bool = False) -> list[RestrictedTopic]:
    """Catalog of optional Restricted Topics for owner configuration.

    Topics are inactive by default. Migration must not auto-restrict recovered Lina files
    from this hardcoded list; the owner activates topics explicitly in the Restricted UI.
    """
    topics: list[RestrictedTopic] = []
    for topic_id in INITIAL_RESTRICTED_TOPIC_IDS:
        labels_raw = INITIAL_RESTRICTED_LABELS[topic_id]
        labels = LocalizedLabels(
            en=labels_raw.get("en", ""),
            ar=labels_raw.get("ar", ""),
            fr=labels_raw.get("fr", ""),
        )
        keywords = [v for v in (labels.en, labels.ar, labels.fr) if v]
        topics.append(
            RestrictedTopic(
                id=topic_id,
                labels=labels,
                keywords=keywords,
                active=active,
            )
        )
    return topics


def initial_restricted_policy(*, active: bool = False) -> RestrictedPolicy:
    """Optional topic catalog. Defaults inactive so content is not auto-restricted."""
    return RestrictedPolicy(topics=initial_restricted_topics(active=active))


def default_section_payload(section: str) -> dict[str, object]:
    """Empty-but-valid draft payload for a CM section."""
    builders: dict[str, CmBaseModel] = {
        "ai_basics": AiBasics(),
        "languages": LanguagePolicy(),
        "style": StylePolicy(),
        "dynamic_messages": DynamicMessagesSection(),
        "services": ServicesSection(),
        "branches": BranchesSection(),
        "prices": PricesSection(),
        "care": CareSection(),
        "knowledge": KnowledgeSection(),
        "faq": FaqSection(),
        "handoff": HandoffPolicy(),
        # Empty by default — Restricted Topics are owner-configured, not auto-seeded.
        "restricted": RestrictedPolicy(),
        "actions": ActionsSection(),
        "ai_limits": AiLimitsSection(),
        "off_days": OffDaysSection(),
    }
    model = builders.get(section)
    if model is None:
        return {}
    return model.model_dump(mode="json")
