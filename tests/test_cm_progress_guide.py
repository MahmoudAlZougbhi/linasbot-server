"""CM shared progress + Owner Copilot smart guide / fill-missing plan."""

from __future__ import annotations

import pytest

from services.cm.constants import CM_SECTIONS
from services.cm.fill_plan import (
    advance_fill_plan,
    cancel_fill_plan,
    get_fill_plan_status,
    skip_fill_plan_section,
    start_fill_plan,
)
from services.cm.progress import progress_summary
from services.cm.progress_quality import assess_section_fill
from services.cm.schemas import default_section_payload
from services.cm.section_guide import guide_for_section, list_section_guides
from services.cm.storage import put_draft
from services.owner_ai_tools_cm_guide import tool_cm_fill_plan, tool_inspect_cm_guide
from services.owner_copilot_v2.tool_schemas import tool_names


@pytest.fixture()
def tenant(tmp_path, monkeypatch: pytest.MonkeyPatch) -> str:
    from pathlib import Path

    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path))
    from storage import persistent_storage as ps

    monkeypatch.setattr(ps, "_DATA_ROOT", Path(tmp_path))
    monkeypatch.setattr(ps, "_LINASBOT_DATA_ROOT", str(tmp_path))
    return "tenant_guide_test"


def test_guide_covers_all_real_sections_only() -> None:
    guides = list_section_guides()
    assert [g["section"] for g in guides] == list(CM_SECTIONS)
    assert guide_for_section("about") is None
    assert guide_for_section("business_hours") is None
    assert guide_for_section("opening_hours") is not None


def test_quality_missing_weak_filled() -> None:
    missing = assess_section_fill("ai_basics", default_section_payload("ai_basics"), is_default=True)
    assert missing["fill"] == "missing"
    assert missing["is_done"] is False

    weak = assess_section_fill(
        "ai_basics",
        {**default_section_payload("ai_basics"), "clinic_name": "Lina"},
        is_default=False,
    )
    assert weak["fill"] == "weak"
    assert "role_or_purpose" in weak["gaps"]

    filled = assess_section_fill(
        "ai_basics",
        {
            **default_section_payload("ai_basics"),
            "clinic_name": "Lina",
            "assistant_name": "Lina AI",
            "ai_role": "clinic assistant",
        },
        is_default=False,
    )
    assert filled["fill"] == "filled"
    assert filled["is_done"] is True


def test_progress_summary_and_fill_plan(tenant: str) -> None:
    summary = progress_summary(tenant, create_missing=False)
    assert summary["total"] == len(CM_SECTIONS)
    # Optional Comments policy defaults count as filled (no owner content required).
    optional_done = {"comments"}
    assert summary["complete"] == len(optional_done)
    assert set(summary["remaining_sections"]) == set(CM_SECTIONS) - optional_done
    assert "cm_fill_plan" in summary["fill_missing_prompt"] or "inspect_cm_guide" in summary["fill_missing_prompt"]

    put_draft(
        "ai_basics",
        payload={
            **default_section_payload("ai_basics"),
            "clinic_name": "Demo Clinic",
            "assistant_name": "Demo",
            "business_purpose": "Help customers book and ask questions",
        },
        if_match=None,
        updated_by="test",
        tenant_id=tenant,
    )
    put_draft(
        "services",
        payload={
            "items": [{"id": "laser", "labels": {"en": "Laser", "ar": "ليزر", "fr": "", "franco": ""}}],
            "notes": None,
        },
        if_match=None,
        updated_by="test",
        tenant_id=tenant,
    )

    summary2 = progress_summary(tenant, create_missing=False)
    assert "ai_basics" in summary2["done_sections"]
    assert "services" in summary2["done_sections"]
    assert "ai_basics" not in summary2["remaining_sections"]

    plan = start_fill_plan(tenant_id=tenant, user_id="owner1")
    assert "ai_basics" in plan["done"]
    assert "services" in plan["done"]
    assert plan["current_section"] not in {"ai_basics", "services"}
    assert plan["focus"]["section"] == plan["current_section"]
    assert plan["status"] == "active"

    skipped = skip_fill_plan_section(tenant_id=tenant, user_id="owner1", section=plan["current_section"])
    assert plan["current_section"] in skipped["skipped"]
    assert skipped["current_section"] != plan["current_section"]

    advanced = advance_fill_plan(tenant_id=tenant, user_id="owner1")
    assert advanced["focus"] is None or advanced["focus"]["section"] == advanced["current_section"]

    status = get_fill_plan_status(tenant_id=tenant, user_id="owner1")
    assert status["plan"] is not None

    cancelled = cancel_fill_plan(tenant_id=tenant, user_id="owner1")
    assert cancelled["cancelled"] is True
    assert get_fill_plan_status(tenant_id=tenant, user_id="owner1")["active"] is False


@pytest.mark.asyncio
async def test_tools_and_schemas(tenant: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "services.owner_ai_tools_cm_guide.resolve_permissions",
        lambda role, _extra: {"contentManagers": True},
    )
    names = tool_names()
    assert "inspect_cm_guide" in names
    assert "cm_fill_plan" in names

    overview = await tool_inspect_cm_guide(tenant_id=tenant, role="admin")
    assert overview.ok is True
    assert "done_sections" in overview.data
    assert overview.data.get("ai_directive")

    plan_res = await tool_cm_fill_plan(tenant_id=tenant, role="admin", user_id="u1", action="start")
    assert plan_res.ok is True
    assert plan_res.data["plan"]["remaining"]
    focus = plan_res.data["plan"]["focus"]["section"]

    one = await tool_inspect_cm_guide(tenant_id=tenant, role="admin", section=focus)
    assert one.ok is True
    assert one.data["section"]["skip_as_done"] is False


@pytest.mark.asyncio
async def test_propose_blocks_done_unless_force(tenant: str, monkeypatch: pytest.MonkeyPatch) -> None:
    from services.owner_ai_tools_write import tool_propose_cm_patch

    monkeypatch.setattr(
        "services.owner_ai_tools_write.resolve_permissions",
        lambda role, _extra: {"contentManagers": True},
    )
    put_draft(
        "ai_basics",
        payload={
            **default_section_payload("ai_basics"),
            "clinic_name": "Done Co",
            "assistant_name": "Done",
            "ai_role": "helper",
        },
        if_match=None,
        updated_by="test",
        tenant_id=tenant,
    )
    blocked = await tool_propose_cm_patch(
        tenant_id=tenant,
        role="admin",
        user_id="u1",
        section="ai_basics",
        patch={"notes": "nope"},
    )
    assert blocked.ok is False
    assert blocked.error == "section_already_filled"

    forced = await tool_propose_cm_patch(
        tenant_id=tenant,
        role="admin",
        user_id="u1",
        section="ai_basics",
        patch={"notes": "owner asked"},
        force_edit=True,
    )
    assert forced.ok is True
    assert forced.requires_confirmation is True
