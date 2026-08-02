"""Pydantic v2 schemas for the Content Management AI Control Plane."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

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
    assistant_name: str = "Linas"
    clinic_name: str = "Linas Laser"
    identity_summary: str = ""
    advanced_instructions: str = ""
    notes: str | None = None


class LanguagePolicy(CmBaseModel):
    supported_languages: tuple[str, ...] = Field(default_factory=lambda: SUPPORTED_LANGUAGES)
    response_language_map: dict[str, str] = Field(default_factory=lambda: dict(RESPONSE_LANGUAGE_MAP))
    default_language: str = "ar"
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
    notes: str | None = None


class HandoffContact(CmBaseModel):
    id: str
    phone_e164: str
    label: str = ""
    branch_id: str | None = None
    gender: GenderAudience = "any"
    topic_id: str | None = None
    notes: str | None = None


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


class ServicesSection(CmBaseModel):
    items: list[ServiceRecord] = Field(default_factory=list)
    notes: str | None = None


class BranchesSection(CmBaseModel):
    items: list[BranchRecord] = Field(default_factory=list)
    notes: str | None = None


class PricesSection(CmBaseModel):
    items: list[PriceRecord] = Field(default_factory=list)
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


class FaqRecord(CmBaseModel):
    qa_group_id: str
    variants: list[FaqVariant] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    notes: str | None = None


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


def initial_restricted_topics() -> list[RestrictedTopic]:
    """Initial Restricted defaults (plan D8) — owner may change before first publish."""
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
                active=True,
            )
        )
    return topics


def initial_restricted_policy() -> RestrictedPolicy:
    return RestrictedPolicy(topics=initial_restricted_topics())


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
        "restricted": initial_restricted_policy(),
    }
    model = builders.get(section)
    if model is None:
        return {}
    return model.model_dump(mode="json")
