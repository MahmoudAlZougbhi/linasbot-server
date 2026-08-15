"""Pydantic v2 schemas for the AI Setup AI Control Plane.

Content/policy models: schemas_content (LOC split).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import Field

from services.cm.constants import (
    CM_SCHEMA_VERSION,
    INITIAL_RESTRICTED_LABELS,
    INITIAL_RESTRICTED_TOPIC_IDS,
)
from services.cm.schemas_content import (  # noqa: F401
    ActionCapability,
    ActionsSection,
    AiBasics,
    ArticleAttachment,
    ArticleRecord,
    Audience,
    BranchDaySchedule,
    BranchHours,
    BranchRecord,
    BranchWeeklySchedule,
    CmBaseModel,
    CommentRule,
    CommentsSection,
    GenderAudience,
    HandoffContact,
    HandoffMatrixRow,
    HandoffPolicy,
    LangCode,
    LanguagePolicy,
    LocalizedLabels,
    PriceRecord,
    RestrictedPolicy,
    RestrictedTopic,
    ServiceRecord,
    StylePolicy,
    ValidationSeverity,
)
from services.cm.schemas_requests import (  # noqa: F401
    RequestAssignmentDefaults,
    RequestCatalogItem,
    RequestFieldDef,
    RequestMessages,
    RequestsAppointmentsSection,
)


class AiLimitsSection(CmBaseModel):
    """Tenant-configurable AI usage limits (enforced from CM ai_limits)."""

    unlimited: bool = False
    # Capability switches (moved from Settings Features into AI Setup).
    voice_processing_enabled: bool = True
    image_analysis_enabled: bool = True
    human_handoff_enabled: bool = True
    text_words_per_message: int = Field(default=500, ge=0)
    text_replies_per_day: int = Field(default=20, ge=0)
    text_replies_per_week: int = Field(default=100, ge=0)
    text_replies_per_month: int = Field(default=300, ge=0)
    photos_per_message: int = Field(default=2, ge=0)
    image_per_day: int = Field(default=5, ge=0)
    image_per_week: int = Field(default=20, ge=0)
    image_per_month: int = Field(default=60, ge=0)
    voice_minutes_per_message: int = Field(default=2, ge=0)
    voice_minutes_per_day: int = Field(default=10, ge=0)
    voice_minutes_per_week: int = Field(default=40, ge=0)
    voice_minutes_per_month: int = Field(default=120, ge=0)
    context_lines_per_day: int = Field(default=500, ge=0)
    context_lines_per_week: int = Field(default=2000, ge=0)
    enforce_image_day: bool = True
    enforce_image_week: bool = True
    enforce_image_month: bool = True
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


class OpeningHoursDay(CmBaseModel):
    """One weekday row: open→close times, or marked closed."""

    closed: bool = False
    open: str = ""  # HH:MM
    close: str = ""  # HH:MM


class OpeningHoursSchedule(CmBaseModel):
    """Named hours calendar (e.g. Men / Women / Branch Beirut)."""

    id: str
    title: str = ""
    monday: OpeningHoursDay = Field(default_factory=OpeningHoursDay)
    tuesday: OpeningHoursDay = Field(default_factory=OpeningHoursDay)
    wednesday: OpeningHoursDay = Field(default_factory=OpeningHoursDay)
    thursday: OpeningHoursDay = Field(default_factory=OpeningHoursDay)
    friday: OpeningHoursDay = Field(default_factory=OpeningHoursDay)
    saturday: OpeningHoursDay = Field(default_factory=OpeningHoursDay)
    sunday: OpeningHoursDay = Field(default_factory=OpeningHoursDay)
    notes: str | None = None

    def summary_line(self) -> str:
        days = (
            ("Mon", self.monday),
            ("Tue", self.tuesday),
            ("Wed", self.wednesday),
            ("Thu", self.thursday),
            ("Fri", self.friday),
            ("Sat", self.saturday),
            ("Sun", self.sunday),
        )
        parts: list[str] = []
        for label, day in days:
            if day.closed:
                parts.append(f"{label}: closed")
            elif (day.open or "").strip() and (day.close or "").strip():
                parts.append(f"{label}: {day.open.strip()}-{day.close.strip()}")
        title = (self.title or "").strip() or self.id
        return f"{title}: " + "; ".join(parts) if parts else title


class OpeningHoursSection(CmBaseModel):
    items: list[OpeningHoursSchedule] = Field(default_factory=list)
    notes: str | None = None


class ServicesSection(CmBaseModel):
    items: list[ServiceRecord] = Field(default_factory=list)
    notes: str | None = None


class BranchesSection(CmBaseModel):
    items: list[BranchRecord] = Field(default_factory=list)
    policy_text: str = ""
    timezone: str = "Asia/Beirut"
    specific_off_rules: list[OffDayRule] = Field(default_factory=list)
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
    """Conditional greeting rule — legacy items without trigger fields default to always."""

    id: str
    enabled: bool = True
    name: str = ""
    trigger_mode: Literal["always", "starts_with", "any_keyword", "session_start"] = "always"
    trigger_pattern: str = ""
    keywords: list[str] = Field(default_factory=list)
    ar: str = ""
    en: str = ""
    fr: str = ""
    notes: str | None = None


class DynamicMessagesSection(CmBaseModel):
    items: list[DynamicMessageRecord] = Field(default_factory=list)
    notes: str | None = None


class FaqVariant(CmBaseModel):
    language: str
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
    source_language: str | None = None
    reviewed: bool = False
    provenance: str | None = None
    revision: int = 1

    def is_complete_for_languages(self, required: list[str] | tuple[str, ...]) -> bool:
        required_set = {str(lang).strip().lower() for lang in required if str(lang).strip()}
        if not required_set:
            return True
        langs = {
            str(v.language).strip().lower()
            for v in self.variants
            if (v.question or "").strip() and (v.answer or "").strip()
        }
        return required_set <= langs

    @property
    def is_complete_four_lang(self) -> bool:
        """Backward-compatible: complete for legacy 4-language default."""
        return self.is_complete_for_languages(("ar", "en", "fr", "franco"))


class FaqSection(CmBaseModel):
    items: list[FaqRecord] = Field(default_factory=list)
    smart_answer_languages: list[str] = Field(default_factory=lambda: ["ar", "en", "fr", "franco"])
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
        "comments": CommentsSection(),
        "ai_limits": AiLimitsSection(),
        "off_days": OffDaysSection(),
        "opening_hours": OpeningHoursSection(),
        "requests_appointments": RequestsAppointmentsSection(),
    }
    model = builders.get(section)
    if model is None:
        return {}
    return model.model_dump(mode="json")
