"""Default CM section payloads (split from schemas.py for line cap)."""

from __future__ import annotations

from services.ai_setup.schemas import (
    ActionsSection,
    AiBasics,
    AiLimitsSection,
    BranchesSection,
    CareSection,
    CmBaseModel,
    CommentsSection,
    DynamicMessagesSection,
    FaqSection,
    HandoffPolicy,
    KnowledgeSection,
    LanguagePolicy,
    OffDaysSection,
    OpeningHoursSection,
    PricesSection,
    RequestsAppointmentsSection,
    RestrictedPolicy,
    ServicesSection,
    StylePolicy,
)
from services.runtime_limits.schema import RuntimeLimitsSection


def default_section_payload(section: str) -> dict[str, object]:
    """Empty-but-valid draft payload, or Sol seed for owner-only sections."""
    from services.owner_copilot.sol_seed import seeded_section_payload

    seeded = seeded_section_payload(section)
    if seeded is not None:
        return seeded
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
        "restricted": RestrictedPolicy(),
        "actions": ActionsSection(),
        "comments": CommentsSection(),
        "ai_limits": AiLimitsSection(),
        "off_days": OffDaysSection(),
        "opening_hours": OpeningHoursSection(),
        "requests_appointments": RequestsAppointmentsSection(),
        "runtime_limits": RuntimeLimitsSection(),
    }
    model = builders.get(section)
    if model is None:
        return {}
    return model.model_dump(mode="json")
