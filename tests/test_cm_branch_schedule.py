"""Unified Location & Opening Hours — schema, migration, runtime derivation."""

from __future__ import annotations

from services.cm.branch_schedule import (
    branches_section_has_unified_schedule,
    derive_off_days_section,
    derive_opening_hours_section,
    empty_weekly_schedule,
    merge_opening_hours_into_branches,
    normalize_branches_payload,
)
from services.cm.schemas import (
    BranchDaySchedule,
    BranchRecord,
    BranchesSection,
    BranchWeeklySchedule,
    LocalizedLabels,
    OpeningHoursDay,
    OpeningHoursSchedule,
    OpeningHoursSection,
)
from services.cm.structured_resolver import resolve_branch_facts, resolve_opening_hours_facts
from services.cm.off_days import resolve_off_day_facts


def test_branch_weekly_schedule_summary() -> None:
    schedule = BranchWeeklySchedule(
        monday=BranchDaySchedule(enabled=True, open="09:00", close="18:00"),
        wednesday=BranchDaySchedule(enabled=True, off_day=True),
        sunday=BranchDaySchedule(enabled=True, open="10:00", close="14:00", note="By appointment"),
    )
    line = schedule.summary_line("Beirut")
    assert "Mon: 09:00-18:00" in line
    assert "Wed: closed" in line
    assert "Sun: 10:00-14:00 (By appointment)" in line


def test_merge_opening_hours_into_empty_branches() -> None:
    oh = OpeningHoursSection(
        items=[
            OpeningHoursSchedule(
                id="men",
                title="Men",
                monday=OpeningHoursDay(open="10:00", close="20:00"),
                tuesday=OpeningHoursDay(closed=True),
            )
        ]
    )
    merged = merge_opening_hours_into_branches({"items": []}, oh.model_dump(mode="json"))
    items = merged["items"]
    assert len(items) == 1
    ws = items[0]["weekly_schedule"]
    assert ws["monday"]["enabled"] is True
    assert ws["monday"]["open"] == "10:00"
    assert ws["tuesday"]["off_day"] is True


def test_derive_opening_hours_from_branches() -> None:
    section = BranchesSection(
        items=[
            BranchRecord(
                id="b1",
                labels=LocalizedLabels(en="Main"),
                weekly_schedule=BranchWeeklySchedule(
                    monday=BranchDaySchedule(enabled=True, open="08:00", close="17:00"),
                ),
            )
        ]
    )
    derived = derive_opening_hours_section(section)
    assert len(derived.items) == 1
    facts = resolve_opening_hours_facts(derived)
    assert any(f.kind == "opening_hours" and "Main:" in f.value for f in facts)


def test_resolve_branch_facts_uses_weekly_schedule() -> None:
    section = BranchesSection(
        items=[
            BranchRecord(
                id="b2",
                labels=LocalizedLabels(en="Jounieh"),
                maps_url="https://maps.example/j",
                weekly_schedule=BranchWeeklySchedule(
                    friday=BranchDaySchedule(enabled=True, open="09:00", close="15:00"),
                ),
            )
        ]
    )
    facts = resolve_branch_facts(section, "b2")
    kinds = {f.kind: f.value for f in facts}
    assert kinds["branch_maps_url"] == "https://maps.example/j"
    assert "Fri: 09:00-15:00" in kinds["branch_hours"]


def test_branches_section_has_unified_schedule() -> None:
    payload = normalize_branches_payload(
        {
            "items": [
                {
                    "id": "x",
                    "labels": {"en": "X"},
                    "weekly_schedule": empty_weekly_schedule(),
                }
            ]
        }
    )
    payload["items"][0]["weekly_schedule"]["monday"]["enabled"] = True
    assert branches_section_has_unified_schedule(payload)


def test_derive_off_days_from_specific_rules() -> None:
    from services.cm.schemas import OffDayRule

    section = BranchesSection(
        timezone="Asia/Beirut",
        specific_off_rules=[
            OffDayRule(id="d1", kind="date", date="2026-12-25", reason="Holiday"),
        ],
    )
    derived = derive_off_days_section(section)
    assert derived.timezone == "Asia/Beirut"
    assert len(derived.rules) == 1
    facts = resolve_off_day_facts(derived, now=__import__("datetime").datetime(2026, 12, 25, 12, 0))
    assert any(f.kind == "business_closed_today" and f.value == "true" for f in facts)
