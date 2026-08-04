"""Content-based CM section classification (no topic-keyword Restricted scrub).

Classifies narrative articles by actual title/body/tags into owner CM homes.
One source may map to multiple derived records (e.g. Service + Knowledge).
Never invents prices/hours/phones/availability — availability is only set when
the source text itself claims offered / not offered, or is an offered-service
training philosophy.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from services.cm.schemas import Audience, LocalizedLabels

PrimaryTarget = Literal[
    "knowledge",
    "care",
    "services",
    "branches",
    "handoff",
    "prices",
    "style",
    "dynamic_messages",
    "ai_basics",
    "faq",
]

_NOT_OFFERED_MARKERS = (
    "not offered",
    "do not offer",
    "don't offer",
    "we don't offer",
    "we do not offer",
    "unsupported",
    "not available",
    "لا نقدّم",
    "لا نقدم",
    "مش متوفر",
    "غير متوفر",
)

_OFFERED_MARKERS = (
    "we offer",
    "is offered",
    "are offered",
    "offered at",
    "available at",
    "نقدم",
    "متوفر",
    "service_id",
)

_CARE_MARKERS = (
    "shave before",
    "shave at home",
    "aftercare",
    "after care",
    "preparation",
    "prep before",
    "pre-care",
    "pre care",
    "قبل الجلسة",
    "بعد الجلسة",
    "تحضير",
)

_LOCATION_MARKERS = (
    "location_rules",
    "<location_rules>",
    "branch hours",
    "opening hours",
    "ramlet",
    "antelias",
    "أنطلياس",
    "بيروت",
    "beirut",
    "where are you",
    "our branches",
    "our locations",
)

_GREETING_MARKERS = (
    "greeting rule",
    "## greeting",
    "welcome message",
    "first message",
    "new user handling",
    "new-user",
    "new customer greeting",
)

_BOOKING_MARKERS = (
    "appointment_rules",
    "</appointment_rules>",
    "booking_creation",
    "existing_appointment",
    "operational_tool",
    "submit_booking_intent",
    "check_next_appointment",
    "human handoff",
    "human handover",
    "whatsapp routing",
    "marwa",
)

_PRICE_MARKERS = (
    "price list",
    "pricing after",
    "beard area pricing",
    "discount",
    "package price",
    "price_list",
    "ll.",
    "ل.ل",
)

_STYLE_MARKERS = (
    "style guide",
    "tone of voice",
    "do not say",
    "don't say",
    "writing style",
    "response style",
)

_SERVICE_SPECS: tuple[tuple[tuple[str, ...], str, LocalizedLabels, str, tuple[str, ...]], ...] = (
    (
        ("tattoo removal", "tattoo_removal", "وشم", "تاتو", "pico"),
        "tattoo_removal",
        LocalizedLabels(en="Laser tattoo removal", ar="إزالة الوشم بالليزر", fr="Détatouage laser"),
        "laser",
        ("tattoo", "وشم", "تاتو", "pico"),
    ),
    (
        ("co2 laser", "co₂ laser", "co2_laser", "resurfacing"),
        "co2_laser",
        LocalizedLabels(en="CO₂ laser", ar="ليزر CO2", fr="Laser CO2"),
        "laser",
        ("co2", "co₂", "resurfacing"),
    ),
    (
        ("dpl", "whitening", "pigmentation", "dpl_whitening"),
        "dpl_whitening",
        LocalizedLabels(en="DPL whitening", ar="تبييض DPL", fr="Blanchiment DPL"),
        "skin",
        ("dpl", "whitening", "تبييض", "pigmentation"),
    ),
    (
        ("laser hair removal", "laser_hair_removal", "hair removal", "épilation", "إزالة الشعر"),
        "laser_hair_removal",
        LocalizedLabels(en="Laser hair removal", ar="إزالة الشعر بالليزر", fr="Épilation laser"),
        "laser",
        ("laser", "hair removal", "ليزر", "épilation"),
    ),
)


@dataclass
class ServiceDerivation:
    id: str
    labels: LocalizedLabels
    available: bool
    category: str
    aliases: list[str] = field(default_factory=list)
    audience: Audience = "general"
    notes: str | None = None


@dataclass
class ArticleClassification:
    source_id: str
    title: str
    source_filename: str | None
    source_checksum: str | None
    targets: list[PrimaryTarget]
    keep_in_knowledge_active: bool
    move_to_care: bool
    archive_from_knowledge: bool
    service_derivations: list[ServiceDerivation] = field(default_factory=list)
    notes_home: PrimaryTarget | None = None
    ai_basics_field: str | None = None
    dynamic_message_id: str | None = None
    rationale: str = ""
    availability_conflicts: list[str] = field(default_factory=list)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _has_any(blob: str, markers: tuple[str, ...]) -> bool:
    return any(marker in blob for marker in markers)


def _availability_from_text(blob: str, *, philosophy: bool) -> bool | None:
    """Return True/False when source claims availability; None when educational-only."""
    if _has_any(blob, _NOT_OFFERED_MARKERS):
        return False
    if philosophy or _has_any(blob, _OFFERED_MARKERS):
        return True
    return None


def _matched_services(blob: str) -> list[tuple[str, LocalizedLabels, str, list[str]]]:
    matched: list[tuple[str, LocalizedLabels, str, list[str]]] = []
    for markers, service_id, labels, category, aliases in _SERVICE_SPECS:
        if any(marker in blob for marker in markers):
            matched.append((service_id, labels, category, list(aliases)))
    return matched


def classify_article(
    *,
    article_id: str,
    title: str,
    body: str,
    tags: list[str] | None = None,
    source_filename: str | None = None,
    source_checksum: str | None = None,
    category: str = "",
) -> ArticleClassification:
    """Classify one article by content. Never routes into Restricted by topic name."""
    tag_list = [str(t) for t in (tags or [])]
    blob = _norm(f"{title}\n{body}\n{' '.join(tag_list)}\n{category}\n{source_filename or ''}")
    title_l = _norm(title)
    philosophy = "philosophy" in title_l or "training_philosophy" in blob

    base = ArticleClassification(
        source_id=article_id,
        title=title,
        source_filename=source_filename,
        source_checksum=source_checksum,
        targets=["knowledge"],
        keep_in_knowledge_active=True,
        move_to_care=False,
        archive_from_knowledge=False,
    )

    # Treatment philosophies must win over care/booking language inside the same body.
    services = _matched_services(blob)
    if services and philosophy:
        availability = _availability_from_text(blob, philosophy=True)
        derivations = [
            ServiceDerivation(
                id=service_id,
                labels=labels,
                available=True if availability is None else availability,
                category=category_name,
                aliases=aliases,
                notes=f"Derived from training philosophy source {source_filename or article_id}.",
            )
            for service_id, labels, category_name, aliases in services
        ]
        base.targets = ["services", "knowledge"]
        base.service_derivations = derivations
        base.keep_in_knowledge_active = True
        base.archive_from_knowledge = False
        base.rationale = "named treatment philosophy — service card + educational knowledge retained"
        return base

    # Foundation KB stays in Knowledge even when the corpus mentions prep/aftercare topics.
    source_l = (source_filename or "").lower()
    if (
        "knowledge base" in title_l
        or category == "foundation"
        or source_l.endswith("knowledge_base.txt")
        or source_l == "knowledge_base.txt"
    ):
        base.targets = ["knowledge"]
        base.keep_in_knowledge_active = True
        base.archive_from_knowledge = False
        base.rationale = "foundation / general clinic education"
        return base

    # Explicit care tags win for prep/aftercare files (not treatment philosophies).
    if any(tag in {"prep", "aftercare", "care", "preparation"} for tag in tag_list) or _has_any(blob, _CARE_MARKERS):
        base.targets = ["care"]
        base.move_to_care = True
        base.keep_in_knowledge_active = False
        base.archive_from_knowledge = True
        base.rationale = "prep/aftercare content"
        return base

    if _has_any(blob, _LOCATION_MARKERS) or "location_rules" in title_l or title_l.strip("<>/ ") == "location_rules":
        base.targets = ["branches"]
        base.notes_home = "branches"
        base.keep_in_knowledge_active = False
        base.archive_from_knowledge = True
        base.rationale = "location/branch routing rules"
        return base

    if _has_any(blob, _GREETING_MARKERS):
        base.targets = ["ai_basics", "dynamic_messages"]
        base.notes_home = "ai_basics"
        base.ai_basics_field = "greeting_behavior" if "greeting" in blob else "short_introduction"
        if "new user" in blob or "new-user" in blob:
            base.ai_basics_field = "short_introduction"
        base.dynamic_message_id = f"redistributed_{article_id}"
        base.keep_in_knowledge_active = False
        base.archive_from_knowledge = True
        base.rationale = "greeting / new-user handling"
        return base

    if _has_any(blob, _BOOKING_MARKERS) or "appointment" in title_l or "booking" in title_l:
        base.targets = ["handoff"]
        base.notes_home = "handoff"
        base.keep_in_knowledge_active = False
        base.archive_from_knowledge = True
        base.rationale = "appointment/booking/handoff operational rules"
        return base

    if _has_any(blob, _STYLE_MARKERS):
        base.targets = ["style"]
        base.notes_home = "style"
        base.keep_in_knowledge_active = False
        base.archive_from_knowledge = True
        base.rationale = "style/tone guidance"
        return base

    # Price narrative (never invent amounts — policy_text/provenance only).
    if (
        _has_any(blob, _PRICE_MARKERS)
        or "pricing" in title_l
        or "price" in title_l
        or "price_list" in (source_filename or "").lower()
        or category == "pricing_source"
    ):
        if "appointment" in blob and "pricing after" in blob:
            base.targets = ["prices", "handoff"]
            base.notes_home = "prices"
        else:
            base.targets = ["prices"]
            base.notes_home = "prices"
        base.keep_in_knowledge_active = False
        base.archive_from_knowledge = True
        base.rationale = "price/provenance text (no invented amounts)"
        return base

    if services:
        availability = _availability_from_text(blob, philosophy=False)
        derivations = []
        for service_id, labels, category_name, aliases in services:
            if availability is None:
                continue
            derivations.append(
                ServiceDerivation(
                    id=service_id,
                    labels=labels,
                    available=availability,
                    category=category_name,
                    aliases=aliases,
                    notes=f"Derived from source {source_filename or article_id}.",
                )
            )
        if derivations:
            base.targets = ["services", "knowledge"]
            base.service_derivations = derivations
            base.keep_in_knowledge_active = True
            base.archive_from_knowledge = False
            base.rationale = "named treatment — service card + educational knowledge retained"
            return base
        base.targets = ["knowledge"]
        base.rationale = "educational treatment text without availability claim"
        return base

    base.rationale = "general clinic education"
    return base


def classify_articles(articles: list[dict[str, Any]]) -> list[ArticleClassification]:
    out: list[ArticleClassification] = []
    for raw in articles:
        if not isinstance(raw, dict):
            continue
        out.append(
            classify_article(
                article_id=str(raw.get("id") or ""),
                title=str(raw.get("title") or ""),
                body=str(raw.get("body") or raw.get("content") or ""),
                tags=[str(t) for t in (raw.get("tags") or [])],
                source_filename=(str(raw["source_filename"]) if raw.get("source_filename") else None),
                source_checksum=(str(raw["source_checksum"]) if raw.get("source_checksum") else None),
                category=str(raw.get("category") or ""),
            )
        )
    return out


def detect_service_availability_conflicts(
    classifications: list[ArticleClassification],
) -> list[dict[str, Any]]:
    """Surface contradictions across sources; never silently pick a winner."""
    by_service: dict[str, list[tuple[str, bool, str]]] = {}
    for row in classifications:
        for spec in row.service_derivations:
            by_service.setdefault(spec.id, []).append((row.source_id, spec.available, row.title))
    conflicts: list[dict[str, Any]] = []
    for service_id, claims in by_service.items():
        truths = {available for _, available, _ in claims}
        if len(truths) > 1:
            conflicts.append(
                {
                    "service_id": service_id,
                    "claims": [
                        {"source_id": sid, "available": available, "title": title} for sid, available, title in claims
                    ],
                    "message": (
                        f"Conflicting availability for service '{service_id}' across sources; "
                        "both preserved for owner review."
                    ),
                }
            )
    return conflicts
