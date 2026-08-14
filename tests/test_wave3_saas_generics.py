"""Wave 3: neutral defaults, booking tools disabled, new CM sections."""

from __future__ import annotations

from services.cm.constants import CM_SECTIONS
from services.cm.schemas import (
    ActionsSection,
    AiBasics,
    AiLimitsSection,
    OffDaysSection,
    OpeningHoursSection,
    default_section_payload,
)
from services.product_features import LEGACY_BOOKING_TOOL_NAMES, legacy_booking_tools_disabled
from utils.utils import get_openai_tools_schema


def test_new_tenant_ai_basics_has_no_linas_defaults() -> None:
    basics = AiBasics()
    payload = default_section_payload("ai_basics")
    assert basics.assistant_name == ""
    assert basics.clinic_name == ""
    assert "Linas" not in str(payload)
    assert "Laser" not in str(payload)
    assert "Marwa" not in str(payload)


def test_cm_sections_include_actions_limits_off_days() -> None:
    assert "actions" in CM_SECTIONS
    assert "ai_limits" in CM_SECTIONS
    assert "off_days" in CM_SECTIONS
    assert "opening_hours" in CM_SECTIONS
    actions = ActionsSection.model_validate(default_section_payload("actions"))
    photo = next(i for i in actions.items if i.id == "photo_analysis")
    assert photo.enabled is False
    limits = AiLimitsSection.model_validate(default_section_payload("ai_limits"))
    assert limits.image_per_day == 5
    off_days = OffDaysSection.model_validate(default_section_payload("off_days"))
    assert off_days.rules == []
    opening = OpeningHoursSection.model_validate(default_section_payload("opening_hours"))
    assert opening.items == []


def test_legacy_booking_tools_never_exposed_to_model() -> None:
    assert legacy_booking_tools_disabled() is True
    tools = get_openai_tools_schema(excluded_tool_names=set(LEGACY_BOOKING_TOOL_NAMES))
    names = {t["function"]["name"] for t in tools}
    for banned in ("submit_booking_intent", "create_appointment", "get_available_slots"):
        assert banned not in names
        assert banned in LEGACY_BOOKING_TOOL_NAMES
