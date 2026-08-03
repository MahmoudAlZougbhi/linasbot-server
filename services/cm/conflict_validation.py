"""Hard publish blockers for Restricted conflicts (plan D4 / T8)."""

from __future__ import annotations

from collections.abc import Iterable

from services.cm.schemas import (
    ArticleRecord,
    FaqRecord,
    FaqSection,
    HandoffPolicy,
    KnowledgeSection,
    PriceRecord,
    PricesSection,
    RestrictedPolicy,
    RestrictedTopic,
    ServiceRecord,
    ServicesSection,
    ValidationFailure,
)

RESTRICTED_SERVICE_AVAILABLE = "RESTRICTED_SERVICE_AVAILABLE"
RESTRICTED_PRICE_PRESENT = "RESTRICTED_PRICE_PRESENT"
RESTRICTED_FAQ_AFFIRMATION = "RESTRICTED_FAQ_AFFIRMATION"
RESTRICTED_KNOWLEDGE_CLAIM = "RESTRICTED_KNOWLEDGE_CLAIM"
RESTRICTED_HANDOFF_MATRIX_ROW = "RESTRICTED_HANDOFF_MATRIX_ROW"

# Affirmative keywords near restricted topics in FAQ/knowledge text.
_AFFIRM_MARKERS = (
    "we offer",
    "we do",
    "available",
    "yes",
    "نقدم",
    "نقدّم",
    "منعمل",
    "نعمل",
    "متوفر",
    "نعم",
    "oui",
    "nous proposons",
    "disponible",
)


def validate_restricted_conflicts(
    *,
    restricted: RestrictedPolicy | dict[str, object],
    services: ServicesSection | list[ServiceRecord] | dict[str, object] | None = None,
    prices: PricesSection | list[PriceRecord] | dict[str, object] | None = None,
    faq: FaqSection | list[FaqRecord] | dict[str, object] | None = None,
    knowledge: KnowledgeSection | list[ArticleRecord] | dict[str, object] | None = None,
    handoff: HandoffPolicy | dict[str, object] | None = None,
) -> list[ValidationFailure]:
    """Return hard blockers when Restricted conflicts with structured content."""
    policy = restricted if isinstance(restricted, RestrictedPolicy) else RestrictedPolicy.model_validate(restricted)
    active = [t for t in policy.topics if t.active]
    if not active:
        return []

    failures: list[ValidationFailure] = []
    service_items = _as_service_items(services)
    price_items = _as_price_items(prices)
    faq_items = _as_faq_items(faq)
    knowledge_items = _as_article_items(knowledge)
    handoff_policy = _as_handoff(handoff)

    for topic in active:
        markers = _topic_markers(topic)
        failures.extend(_check_services(topic, markers, service_items))
        failures.extend(_check_prices(topic, markers, price_items, service_items))
        failures.extend(_check_faq(topic, markers, faq_items))
        failures.extend(_check_knowledge(topic, markers, knowledge_items))
        failures.extend(_check_handoff(topic, markers, handoff_policy))
    return failures


def _topic_markers(topic: RestrictedTopic) -> set[str]:
    markers: set[str] = {topic.id.lower()}
    for label in (topic.labels.en, topic.labels.ar, topic.labels.fr, topic.labels.franco):
        if label.strip():
            markers.add(label.strip().lower())
    for keyword in topic.keywords:
        if keyword.strip():
            markers.add(keyword.strip().lower())
    return markers


def _text_mentions(text: str, markers: set[str]) -> bool:
    lowered = (text or "").lower()
    if not lowered:
        return False
    return any(marker in lowered for marker in markers if marker)


def _is_affirmation(text: str) -> bool:
    lowered = (text or "").lower()
    return any(marker in lowered for marker in _AFFIRM_MARKERS)


def _check_services(
    topic: RestrictedTopic,
    markers: set[str],
    services: list[ServiceRecord],
) -> list[ValidationFailure]:
    out: list[ValidationFailure] = []
    for service in services:
        if not service.available:
            continue
        service_text = " ".join(
            [
                service.id,
                service.labels.en,
                service.labels.ar,
                service.labels.fr,
                *service.aliases,
            ]
        )
        if service.id == topic.id or _text_mentions(service_text, markers):
            out.append(
                ValidationFailure(
                    code=RESTRICTED_SERVICE_AVAILABLE,
                    message=(f"Restricted topic '{topic.id}' conflicts with available service '{service.id}'."),
                    path=f"services.items[{service.id}]",
                    details={"topic_id": topic.id, "service_id": service.id},
                )
            )
    return out


def _check_prices(
    topic: RestrictedTopic,
    markers: set[str],
    prices: list[PriceRecord],
    services: list[ServiceRecord],
) -> list[ValidationFailure]:
    out: list[ValidationFailure] = []
    service_by_id = {s.id: s for s in services}
    for price in prices:
        service = service_by_id.get(price.service_id)
        service_blob = ""
        if service is not None:
            service_blob = " ".join(
                [service.id, service.labels.en, service.labels.ar, service.labels.fr, *service.aliases]
            )
        if price.service_id == topic.id or _text_mentions(service_blob, markers):
            out.append(
                ValidationFailure(
                    code=RESTRICTED_PRICE_PRESENT,
                    message=(
                        f"Restricted topic '{topic.id}' has price row '{price.id}' for service '{price.service_id}'."
                    ),
                    path=f"prices.items[{price.id}]",
                    details={"topic_id": topic.id, "price_id": price.id},
                )
            )
    return out


def _check_faq(
    topic: RestrictedTopic,
    markers: set[str],
    faq_items: list[FaqRecord],
) -> list[ValidationFailure]:
    out: list[ValidationFailure] = []
    for item in faq_items:
        for variant in item.variants:
            blob = f"{variant.question}\n{variant.answer}"
            if _text_mentions(blob, markers) and _is_affirmation(variant.answer):
                out.append(
                    ValidationFailure(
                        code=RESTRICTED_FAQ_AFFIRMATION,
                        message=(f"FAQ group '{item.qa_group_id}' affirms restricted topic '{topic.id}'."),
                        path=f"faq.items[{item.qa_group_id}].{variant.language}",
                        details={"topic_id": topic.id, "qa_group_id": item.qa_group_id},
                    )
                )
                break
    return out


def _check_knowledge(
    topic: RestrictedTopic,
    markers: set[str],
    articles: list[ArticleRecord],
) -> list[ValidationFailure]:
    out: list[ValidationFailure] = []
    for article in articles:
        blob = f"{article.title}\n{article.body}"
        if _text_mentions(blob, markers) and _is_affirmation(blob):
            out.append(
                ValidationFailure(
                    code=RESTRICTED_KNOWLEDGE_CLAIM,
                    message=(f"Knowledge article '{article.id}' claims restricted topic '{topic.id}'."),
                    path=f"knowledge.items[{article.id}]",
                    details={"topic_id": topic.id, "article_id": article.id},
                )
            )
    return out


def _check_handoff(
    topic: RestrictedTopic,
    markers: set[str],
    handoff: HandoffPolicy,
) -> list[ValidationFailure]:
    out: list[ValidationFailure] = []
    for row in handoff.matrix:
        if not row.enabled:
            continue
        row_ids = {value for value in (row.service_id, row.topic_id) if value}
        if topic.id in row_ids or any(m == (row.topic_id or "").lower() for m in markers):
            out.append(
                ValidationFailure(
                    code=RESTRICTED_HANDOFF_MATRIX_ROW,
                    message=(f"Handoff matrix row '{row.id}' routes restricted topic '{topic.id}'."),
                    path=f"handoff.matrix[{row.id}]",
                    details={"topic_id": topic.id, "row_id": row.id},
                )
            )
            continue
        for contact in handoff.contacts:
            if contact.id != row.contact_id:
                continue
            if contact.topic_id == topic.id or _text_mentions(contact.label, markers):
                out.append(
                    ValidationFailure(
                        code=RESTRICTED_HANDOFF_MATRIX_ROW,
                        message=(
                            f"Handoff contact '{contact.id}' on row '{row.id}' targets restricted topic '{topic.id}'."
                        ),
                        path=f"handoff.matrix[{row.id}]",
                        details={"topic_id": topic.id, "row_id": row.id},
                    )
                )
    return out


def _as_service_items(
    value: ServicesSection | list[ServiceRecord] | dict[str, object] | None,
) -> list[ServiceRecord]:
    if value is None:
        return []
    if isinstance(value, ServicesSection):
        return list(value.items)
    if isinstance(value, list):
        return [s if isinstance(s, ServiceRecord) else ServiceRecord.model_validate(s) for s in value]
    section = ServicesSection.model_validate(value)
    return list(section.items)


def _as_price_items(
    value: PricesSection | list[PriceRecord] | dict[str, object] | None,
) -> list[PriceRecord]:
    if value is None:
        return []
    if isinstance(value, PricesSection):
        return list(value.items)
    if isinstance(value, list):
        return [p if isinstance(p, PriceRecord) else PriceRecord.model_validate(p) for p in value]
    section = PricesSection.model_validate(value)
    return list(section.items)


def _as_faq_items(
    value: FaqSection | list[FaqRecord] | dict[str, object] | None,
) -> list[FaqRecord]:
    if value is None:
        return []
    if isinstance(value, FaqSection):
        return list(value.items)
    if isinstance(value, list):
        return [f if isinstance(f, FaqRecord) else FaqRecord.model_validate(f) for f in value]
    section = FaqSection.model_validate(value)
    return list(section.items)


def _as_article_items(
    value: KnowledgeSection | list[ArticleRecord] | dict[str, object] | None,
) -> list[ArticleRecord]:
    if value is None:
        return []
    if isinstance(value, KnowledgeSection):
        return list(value.items)
    if isinstance(value, list):
        return [a if isinstance(a, ArticleRecord) else ArticleRecord.model_validate(a) for a in value]
    section = KnowledgeSection.model_validate(value)
    return list(section.items)


def _as_handoff(value: HandoffPolicy | dict[str, object] | None) -> HandoffPolicy:
    if value is None:
        return HandoffPolicy()
    if isinstance(value, HandoffPolicy):
        return value
    return HandoffPolicy.model_validate(value)


def collect_conflict_codes(failures: Iterable[ValidationFailure]) -> list[str]:
    return [f.code for f in failures]
