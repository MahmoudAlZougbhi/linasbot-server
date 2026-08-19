"""Luna selects one branch; Terra gets that branch plus closed-day exceptions."""

from __future__ import annotations

import json

import pytest

from tests.cm_test_helpers import publish_pointer_content
from tests.customer_reply_ai_v2_helpers import _rich_sections

pytest_plugins = ("tests.customer_reply_ai_v2_fixtures",)


def _twenty_branches() -> list[dict]:
    rows = []
    for i in range(20):
        name = "Beirut Hamra" if i == 2 else f"Branch {i}"
        rows.append(
            {
                "id": f"br{i}",
                "labels": {"en": name, "ar": "فرع 2" if i == 2 else f"فرع {i}", "fr": name},
                "address": "Hamra" if i == 2 else f"Address {i}",
                "street": "Hamra Street" if i == 2 else "",
                "maps_url": "https://maps.example/beirut" if i == 2 else "",
                "weekly_schedule": {
                    "monday": {"enabled": True, "open": "09:00", "close": "18:00", "off_day": False},
                    "sunday": {"enabled": True, "open": "", "close": "", "off_day": True},
                },
                "notes": "Hamra parking in the back" if i == 2 else f"Note {i}",
                "available": True,
                "ai_search_title": "Beirut Hamra Branch" if i == 2 else f"Branch {i} Location",
                "ai_search_description": "Contains Beirut Hamra location, hours, notes, and map link."
                if i == 2
                else f"Contains branch {i} location details.",
            }
        )
    return rows


@pytest.mark.asyncio
async def test_luna_selects_one_branch_of_twenty(v2_env) -> None:
    from services.customer_reply_v2.retrieval_luna import run_retrieval_luna

    sections = _rich_sections()
    sections["branches"] = {
        "items": _twenty_branches(),
        "specific_off_rules": [{"id": "xmas", "kind": "date", "date": "2026-12-25", "reason": "Christmas"}],
        "timezone": "Asia/Beirut",
    }
    sections["off_days"] = {
        "timezone": "Asia/Beirut",
        "rules": [
            {"id": "sun", "kind": "weekly", "weekday": 6, "reason": "Sunday closed"},
            {"id": "eid", "kind": "date", "date": "2026-03-20", "reason": "Holiday"},
        ],
        "notes": "Holiday schedule",
    }
    sections["opening_hours"] = {
        "items": [
            {
                "id": "oh1",
                "title": "ساعات",
                "monday": {"closed": False, "open": "09:00", "close": "18:00"},
                "sunday": {"closed": True, "open": "", "close": ""},
                "ai_search_title": "Weekly Opening Hours",
                "ai_search_description": "Weekday open and close times.",
            }
        ]
    }
    publish_pointer_content("t_br20", sections)

    result = await run_retrieval_luna(
        tenant_id="t_br20",
        message="فرع بيروت لأي ساعة فاتح اليوم؟ ووين مكانه؟",
        customer_profile={},
        scripted_tool_calls=[
            [
                {
                    "name": "read_published_cm_items",
                    "arguments": {"item_ids": ["branches:br2", "opening_hours:oh1"]},
                }
            ],
            {
                "final_plan": {
                    "evidence_status": "sufficient",
                    "selected_source_ids": ["branches:br2", "opening_hours:oh1"],
                    "recommended_tera_effort": "medium",
                }
            },
        ],
    )
    bodies = " ".join(e.content for e in result.evidence)
    ids = {e.source_id for e in result.evidence}
    assert ids == {"branches:br2", "opening_hours:oh1"}
    assert "Hamra" in bodies
    assert "09:00" in bodies
    assert "Sunday closed" in bodies or "weekly_off_days" in bodies
    assert "Christmas" in bodies
    assert "Address 19" not in bodies
    assert "Branch 19" not in bodies
    for e in result.evidence:
        assert "Contains Beirut Hamra location" not in e.content
        parsed = json.loads(e.content)
        assert "ai_search_title" not in parsed
        assert "ai_search_description" not in parsed


@pytest.mark.asyncio
async def test_selected_branch_includes_closed_days_not_other_branches(v2_env) -> None:
    from services.customer_reply_v2.retrieval_tools import ToolContext, dispatch_retrieval_tool

    sections = _rich_sections()
    sections["branches"] = {"items": _twenty_branches(), "specific_off_rules": []}
    sections["off_days"] = {
        "timezone": "Asia/Beirut",
        "rules": [{"id": "sun", "kind": "weekly", "weekday": 6, "reason": "Sunday closed"}],
    }
    revision = publish_pointer_content("t_br_read", sections)
    ctx = ToolContext(tenant_id="t_br_read", published_revision=revision, channel="instagram_dm")
    out = dispatch_retrieval_tool("read_published_cm_items", {"item_ids": ["branches:br2"]}, ctx)
    assert out["ok"] is True
    assert len(out["data"]["evidence"]) == 1
    content = out["data"]["evidence"][0]["content"]
    parsed = json.loads(content)
    assert parsed["id"] == "br2"
    assert "Hamra" in str(parsed)
    assert "Sunday closed" in str(parsed.get("tenant_closed_days"))
    assert "br19" not in content
    assert parsed.get("ai_search_description") is None
