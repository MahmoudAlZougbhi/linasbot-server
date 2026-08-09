"""Opening Hours CM section schema + AI fact resolution."""

from __future__ import annotations

from services.cm.constants import CM_SECTIONS
from services.cm.schemas import (
    OpeningHoursDay,
    OpeningHoursSchedule,
    OpeningHoursSection,
    default_section_payload,
)
from services.cm.structured_resolver import resolve_opening_hours_facts


def test_opening_hours_in_cm_sections() -> None:
    assert "opening_hours" in CM_SECTIONS
    assert CM_SECTIONS.index("opening_hours") == CM_SECTIONS.index("branches") + 1


def test_opening_hours_default_payload() -> None:
    section = OpeningHoursSection.model_validate(default_section_payload("opening_hours"))
    assert section.items == []
    assert section.notes is None


def test_opening_hours_schedule_summary_and_facts() -> None:
    schedule = OpeningHoursSchedule(
        id="men",
        title="Men",
        monday=OpeningHoursDay(open="10:00", close="20:00"),
        tuesday=OpeningHoursDay(open="10:00", close="20:00"),
        wednesday=OpeningHoursDay(closed=True),
        thursday=OpeningHoursDay(open="10:00", close="20:00"),
        friday=OpeningHoursDay(open="10:00", close="20:00"),
        saturday=OpeningHoursDay(open="10:00", close="18:00"),
        sunday=OpeningHoursDay(closed=True),
    )
    summary = schedule.summary_line()
    assert summary.startswith("Men:")
    assert "Mon: 10:00-20:00" in summary
    assert "Wed: closed" in summary
    assert "Sun: closed" in summary

    section = OpeningHoursSection(items=[schedule], notes="By appointment weekends")
    facts = resolve_opening_hours_facts(section)
    kinds = {f.kind for f in facts}
    assert "opening_hours" in kinds
    assert "opening_hours_section_notes" in kinds
    oh = next(f for f in facts if f.kind == "opening_hours")
    assert oh.source_id == "opening_hours:men"
    assert "Men:" in oh.value
