"""Luna selects request rules; Terra receives only those rules."""

from __future__ import annotations

import pytest

from services.cm.request_rules import format_request_rules_for_ai
from tests.cm_test_helpers import publish_pointer_content
from tests.customer_reply_ai_v2_helpers import _rich_sections

pytest_plugins = ("tests.customer_reply_ai_v2_fixtures",)


def _six_hundred_rules() -> dict:
    return {
        "module_enabled": True,
        "enabled_types": ["APPOINTMENT", "ORDER", "OTHER"],
        "rules": [
            {
                "id": f"r{i}",
                "type": "APPOINTMENT" if i != 8 else "ORDER",
                "name": f"قاعدة {i}" if i != 422 else "حجز موعد بيروت",
                "notes": "يجمع تاريخ الموعد" if i == 422 else f"notes {i}",
                "enabled": True,
                "ai_search_title": "Beirut Appointment Booking" if i == 422 else f"Request Rule {i}",
                "ai_search_description": "Captures appointment date and phone."
                if i == 422
                else f"Request rule {i} notes.",
            }
            for i in range(600)
        ],
    }


@pytest.mark.asyncio
async def test_luna_selects_one_of_600_request_rules_for_terra(v2_env) -> None:
    from services.customer_reply_v2.answer_luna import build_answer_messages
    from services.customer_reply_v2.retrieval_luna import run_retrieval_luna

    sections = _rich_sections()
    sections["requests_appointments"] = _six_hundred_rules()
    revision = publish_pointer_content("t_req600", sections)

    from services.customer_reply_v2.operational_titles import collect_operational_titles, inline_titles_for_luna
    from services.customer_reply_v2.retrieval_tools import ToolContext, dispatch_retrieval_tool

    titles = collect_operational_titles({"requests_appointments": sections["requests_appointments"]})
    inline = inline_titles_for_luna(titles)
    inline_ids = {str(row.get("id")) for row in inline["operational_titles"]}
    assert "requests_appointments:r7" in inline_ids
    assert "requests_appointments:r422" in inline_ids
    assert "requests_appointments:r599" in inline_ids
    assert inline["operational_priority_title_count"] == 600

    listed = dispatch_retrieval_tool(
        "list_published_cm_items",
        {"section_ids": ["requests_appointments"]},
        ToolContext(tenant_id="t_req600", published_revision=revision, channel="instagram_dm"),
    )
    assert listed["ok"] is True
    assert len(listed["data"]["items"]) == 600

    retrieval = await run_retrieval_luna(
        tenant_id="t_req600",
        message="بدي احجز موعد بكرا",
        customer_profile={},
        scripted_tool_calls=[
            [
                {
                    "name": "read_published_cm_items",
                    "arguments": {"item_ids": ["requests_appointments:r422"]},
                }
            ],
            {
                "final_plan": {
                    "evidence_status": "sufficient",
                    "selected_source_ids": ["requests_appointments:r422"],
                    "recommended_tera_effort": "medium",
                }
            },
        ],
    )
    assert [e.source_id for e in retrieval.evidence] == ["requests_appointments:r422"]
    assert all("قاعدة 599" not in e.content for e in retrieval.evidence)
    assert all("قاعدة 7" not in e.content for e in retrieval.evidence)

    selected_ids = [
        sid
        for sid in list(retrieval.selected_source_ids or []) + [e.source_id for e in retrieval.evidence]
        if str(sid).startswith("requests_appointments:") or str(sid).startswith("requests:")
    ]
    guidance = format_request_rules_for_ai(sections["requests_appointments"], selected_ids=selected_ids)
    assert "حجز موعد بيروت" in guidance
    assert "قاعدة 1" not in guidance
    assert "قاعدة 599" not in guidance
    assert "قاعدة 7" not in guidance
    assert guidance.count("- [") == 1

    messages = build_answer_messages(
        message="بدي احجز موعد بكرا",
        fixed_context={
            "published_revision": "v",
            "ai_basics": {"advanced_instructions": "x"},
            "style": {"style_body": "y"},
        },
        evidence=list(retrieval.evidence),
        evidence_status="sufficient",
        customer_profile={},
        history_messages=[],
        comment_context=None,
        channel="instagram_dm",
        published_revision="v",
        response_language="ar",
        request_capture_guidance=guidance,
    )
    blob = str(messages)
    assert "حجز موعد بيروت" in blob
    assert "قاعدة 599" not in blob
    assert "notes 599" not in blob
