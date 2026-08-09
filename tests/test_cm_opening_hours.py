"""Opening Hours CM section schema + AI fact resolution."""

from __future__ import annotations

import pytest

from services.cm.constants import CM_SECTIONS
from services.cm.runtime_pipeline import prepare_response
from services.cm.schemas import (
    OpeningHoursDay,
    OpeningHoursSchedule,
    OpeningHoursSection,
    default_section_payload,
)
from services.cm.structured_resolver import resolve_opening_hours_facts
from tests.cm_test_helpers import install_mocked_openai_embeddings, publish_test_content


@pytest.fixture(autouse=True)
def _openai_published_embeddings(monkeypatch: pytest.MonkeyPatch) -> None:
    install_mocked_openai_embeddings(monkeypatch, published_mode=True)


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


@pytest.mark.asyncio
async def test_prepare_response_includes_opening_hours_facts() -> None:
    tenant_id = "cm_opening_hours_runtime"
    await publish_test_content(
        tenant_id,
        {
            "opening_hours": OpeningHoursSection(
                items=[
                    OpeningHoursSchedule(
                        id="women",
                        title="Women",
                        monday=OpeningHoursDay(open="09:00", close="17:00"),
                        sunday=OpeningHoursDay(closed=True),
                    )
                ]
            ).model_dump(mode="json"),
            "faq": {"items": []},
        },
    )
    outcome = await prepare_response(
        tenant_id=tenant_id,
        message="What are your opening hours?",
        detected_language="en",
        response_language="en",
    )
    assert outcome.stop is False
    assert outcome.packet is not None
    assert any(f.kind == "opening_hours" and "Women:" in f.value for f in outcome.packet.facts)
