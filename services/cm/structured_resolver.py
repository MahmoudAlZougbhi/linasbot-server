"""Structured fact resolution from published CM content (plan §9 / §12 steps 5, 6, 11).

Pure, deterministic, no network calls. Restricted-topic detection here is independent of the
Query Interpreter so it can run safely BEFORE any FAQ/interpreter step (plan §12 step 5).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from services.cm.schemas import (
    AnswerFact,
    BranchesSection,
    HandoffMatrixRow,
    HandoffPolicy,
    OpeningHoursSection,
    PricesSection,
    RestrictedPolicy,
    RestrictedTopic,
    ServicesSection,
)


def _topic_markers(topic: RestrictedTopic) -> list[str]:
    return [
        m
        for m in [topic.id, topic.labels.en, topic.labels.ar, topic.labels.fr, topic.labels.franco, *topic.keywords]
        if m
    ]


def _text_mentions(text: str, markers: list[str]) -> bool:
    lowered = (text or "").lower()
    if not lowered:
        return False
    return any(marker.lower() in lowered for marker in markers)


def active_restricted_ids(restricted: RestrictedPolicy | dict[str, Any]) -> set[str]:
    policy = restricted if isinstance(restricted, RestrictedPolicy) else RestrictedPolicy.model_validate(restricted)
    return {topic.id for topic in policy.topics if topic.active}


def find_restricted_topic(
    message: str,
    restricted: RestrictedPolicy | dict[str, Any],
) -> RestrictedTopic | None:
    """Deterministic restricted-topic detection (plan §12 step 5 — runs BEFORE handoff/FAQ)."""
    policy = restricted if isinstance(restricted, RestrictedPolicy) else RestrictedPolicy.model_validate(restricted)
    for topic in policy.topics:
        if topic.active and _text_mentions(message, _topic_markers(topic)):
            return topic
    return None


@dataclass
class HandoffResolution:
    destination_type: str | None
    destination_value: str | None
    contact_label: str
    matched_row_id: str | None
    missing_reason: str | None = None

    @property
    def contact_phone_e164(self) -> str | None:
        """Back-compat: phone/whatsapp destinations expose digits/value as phone-like."""
        if not self.destination_value:
            return None
        if (self.destination_type or "") in {"phone", "whatsapp"}:
            return self.destination_value
        return None


def resolve_handoff(
    handoff: HandoffPolicy | dict[str, Any],
    *,
    service_id: str | None = None,
    topic_id: str | None = None,
    branch_id: str | None = None,
    gender: str | None = None,
) -> HandoffResolution:
    """Resolve the best-matching enabled handoff matrix row to a contact destination.

    Never invents a destination: returns ``missing_reason`` when nothing is configured.
    """
    policy = handoff if isinstance(handoff, HandoffPolicy) else HandoffPolicy.model_validate(handoff)
    contacts_by_id = {contact.id: contact for contact in policy.contacts}

    def _score(row: HandoffMatrixRow) -> int:
        score = 0
        if service_id and row.service_id == service_id:
            score += 4
        if topic_id and row.topic_id == topic_id:
            score += 4
        if branch_id and row.branch_id == branch_id:
            score += 2
        if gender and row.gender == gender:
            score += 1
        return score

    candidates = [row for row in policy.matrix if row.enabled]
    if not candidates:
        # Fall back to first contact with any destination when matrix empty.
        for contact in policy.contacts:
            dtype, value = contact.resolved_destination()
            if value:
                return HandoffResolution(dtype, value, contact.label or contact.id, None)
        return HandoffResolution(None, None, "", None, missing_reason="NO_HANDOFF_ROWS")

    candidates.sort(key=_score, reverse=True)
    best = candidates[0]
    matched = contacts_by_id.get(best.contact_id)
    if matched is None:
        return HandoffResolution(None, None, "", best.id, missing_reason="CONTACT_NOT_FOUND")
    dtype, value = matched.resolved_destination()
    if not value:
        return HandoffResolution(None, None, "", best.id, missing_reason="CONTACT_NOT_FOUND")
    return HandoffResolution(dtype, value, matched.label or matched.id, best.id)


def resolve_service_facts(services: ServicesSection | dict[str, Any], service_id: str) -> list[AnswerFact]:
    section = services if isinstance(services, ServicesSection) else ServicesSection.model_validate(services)
    for service in section.items:
        if service.id == service_id:
            return [
                AnswerFact(
                    kind="service_available",
                    value="true" if service.available else "false",
                    source_id=f"service:{service.id}",
                )
            ]
    return []


def resolve_price_facts(prices: PricesSection | dict[str, Any], service_id: str) -> list[AnswerFact]:
    from services.cm.pricing.section import normalize_prices_section, section_catalog_items, section_price_entries

    section = normalize_prices_section(prices if isinstance(prices, dict) else prices.model_dump(mode="json"))
    facts: list[AnswerFact] = []
    # Prefer generic catalog/price_entries (item id or legacy service_id match).
    for entry in section_price_entries(section):
        if entry.catalog_item_id != service_id:
            continue
        if not entry.active:
            continue
        facts.append(
            AnswerFact(kind="price", value=f"{entry.amount} {entry.currency}", source_id=f"price_entry:{entry.id}")
        )
    if facts:
        return facts
    for item in section_catalog_items(section):
        if item.id != service_id or item.base_price is None or not item.active:
            continue
        facts.append(
            AnswerFact(
                kind="price",
                value=f"{item.base_price} {item.currency}",
                source_id=f"catalog_base:{item.id}",
            )
        )
    if facts:
        return facts
    # Legacy PriceRecord rows
    legacy = prices if isinstance(prices, PricesSection) else PricesSection.model_validate(prices)
    for price in legacy.items:
        if price.service_id != service_id:
            continue
        facts.append(AnswerFact(kind="price", value=f"{price.amount} {price.currency}", source_id=f"price:{price.id}"))
    return facts


def resolve_branch_facts(branches: BranchesSection | dict[str, Any], branch_id: str) -> list[AnswerFact]:
    section = branches if isinstance(branches, BranchesSection) else BranchesSection.model_validate(branches)
    for branch in section.items:
        if branch.id != branch_id:
            continue
        address_value = branch.composed_address()
        facts: list[AnswerFact] = []
        if address_value:
            facts.append(AnswerFact(kind="branch_address", value=address_value, source_id=f"branch:{branch.id}"))
        if (branch.maps_url or "").strip():
            facts.append(
                AnswerFact(
                    kind="branch_maps_url",
                    value=branch.maps_url.strip(),
                    source_id=f"branch:{branch.id}:maps",
                )
            )
        if branch.hours.summary:
            facts.append(AnswerFact(kind="branch_hours", value=branch.hours.summary, source_id=f"branch:{branch.id}"))
        if branch.notes:
            facts.append(AnswerFact(kind="branch_notes", value=branch.notes, source_id=f"branch:{branch.id}:notes"))
        if section.policy_text:
            facts.append(
                AnswerFact(kind="branches_policy", value=section.policy_text, source_id="branches:policy_text")
            )
        return facts
    return []


def resolve_opening_hours_facts(opening_hours: OpeningHoursSection | dict[str, Any]) -> list[AnswerFact]:
    """Expose named opening-hours schedules as grounded facts for the AI."""
    section = (
        opening_hours
        if isinstance(opening_hours, OpeningHoursSection)
        else OpeningHoursSection.model_validate(opening_hours or {})
    )
    facts: list[AnswerFact] = []
    for schedule in section.items:
        summary = schedule.summary_line()
        if summary:
            facts.append(
                AnswerFact(
                    kind="opening_hours",
                    value=summary,
                    source_id=f"opening_hours:{schedule.id}",
                )
            )
        if schedule.notes:
            facts.append(
                AnswerFact(
                    kind="opening_hours_notes",
                    value=schedule.notes,
                    source_id=f"opening_hours:{schedule.id}:notes",
                )
            )
    if section.notes:
        facts.append(
            AnswerFact(kind="opening_hours_section_notes", value=section.notes, source_id="opening_hours:notes")
        )
    return facts


def resolve_service_catalog_facts(services: ServicesSection | dict[str, Any]) -> list[AnswerFact]:
    """Expose available services as grounded facts (no invented services)."""
    section = services if isinstance(services, ServicesSection) else ServicesSection.model_validate(services)
    facts: list[AnswerFact] = []
    for service in section.items:
        label = service.labels.en or service.labels.ar or service.id
        facts.append(
            AnswerFact(
                kind="service_catalog",
                value=f"{label} available={service.available}",
                source_id=f"service:{service.id}",
            )
        )
        if service.notes:
            facts.append(AnswerFact(kind="service_notes", value=service.notes, source_id=f"service:{service.id}:notes"))
    return facts


def resolve_handoff_phone_facts(
    handoff: HandoffPolicy | dict[str, Any],
    *,
    service_id: str | None = None,
    topic_id: str | None = None,
    branch_id: str | None = None,
    gender: str | None = None,
) -> list[AnswerFact]:
    """AnswerFact wrapper around :func:`resolve_handoff` for packet assembly."""
    resolution = resolve_handoff(handoff, service_id=service_id, topic_id=topic_id, branch_id=branch_id, gender=gender)
    if not resolution.destination_value:
        return []
    facts = [
        AnswerFact(
            kind="handoff_destination",
            value=f"{resolution.destination_type}:{resolution.destination_value}",
            source_id=f"handoff:{resolution.matched_row_id or 'unknown'}",
        )
    ]
    if resolution.contact_phone_e164:
        facts.append(
            AnswerFact(
                kind="handoff_phone",
                value=resolution.contact_phone_e164,
                source_id=f"handoff:{resolution.matched_row_id or 'unknown'}",
            )
        )
    return facts
