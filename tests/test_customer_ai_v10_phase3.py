"""Customer AI V10 Phase 3 — Luna low, Tera low/medium, operational titles."""

from __future__ import annotations

import pytest

from tests.cm_test_helpers import publish_test_content
from tests.customer_reply_ai_v2_helpers import _rich_sections

pytest_plugins = ("tests.customer_reply_ai_v2_fixtures",)


def test_luna_retrieval_policy_is_low(v2_env):
    from services.model_policy import resolve_customer_retrieval_policy

    assert resolve_customer_retrieval_policy().reasoning_effort == "low"


def test_invalid_tera_recommendation_becomes_medium():
    from services.customer_reply_v2.tera_llm import normalize_tera_effort

    assert normalize_tera_effort("low") == "low"
    assert normalize_tera_effort("medium") == "medium"
    assert normalize_tera_effort("high") == "medium"
    assert normalize_tera_effort("xhigh") == "medium"
    assert normalize_tera_effort("none") == "medium"
    assert normalize_tera_effort(None) == "medium"


def test_operational_titles_include_nested_and_hundred_children():
    from services.customer_reply_v2.operational_titles import collect_operational_titles, page_operational_titles

    children = [{"id": f"c{i}", "title": f"Child {i}", "status": "active"} for i in range(100)]
    sections = {
        "ai_basics": {"advanced_instructions": "secret"},
        "style": {"style_body": "secret"},
        "services": {
            "items": [
                {
                    "id": "svc_root",
                    "title": "Root service",
                    "status": "active",
                    "children": children,
                }
            ]
        },
        "comments": {
            "rules": [{"id": "rule_price", "name": "Price guidance", "enabled": True, "action": "reply_comment"}]
        },
    }
    titles = collect_operational_titles(sections)
    ids = {t["id"] for t in titles}
    assert "services:svc_root" in ids
    assert "services:c0" in ids
    assert "services:c99" in ids
    assert "comments:rule_price" in ids
    assert not any("secret" in str(t) for t in titles)
    assert not any(t["type"] == "ai_basics" for t in titles)
    page = page_operational_titles(titles, offset=0, limit=80)
    assert page["has_more"] is True
    assert page["total"] == 102
    assert len(page["titles"]) == 80


@pytest.mark.asyncio
async def test_parent_read_does_not_dump_children(v2_env):
    await publish_test_content("t_titles", _rich_sections())
    from services.customer_reply_v2.manifest import get_cached_manifest
    from services.customer_reply_v2.retrieval_tools import ToolContext, dispatch_retrieval_tool

    rev, _ = get_cached_manifest("t_titles")
    ctx = ToolContext(tenant_id="t_titles", published_revision=rev, channel="instagram_dm")
    out = dispatch_retrieval_tool("read_published_cm_items", {"item_ids": ["services:svc_full"]}, ctx)
    assert out["ok"] is True
    evidence = out["data"]["evidence"]
    assert len(evidence) == 1
    assert evidence[0]["source_id"] == "services:svc_full"
    assert "svc_full" in evidence[0]["content"] or "Full" in evidence[0]["title"]


@pytest.mark.asyncio
async def test_large_file_is_explicit_not_silent(v2_env, monkeypatch: pytest.MonkeyPatch):
    await publish_test_content("t_big", _rich_sections())
    from services.customer_reply_v2.manifest import get_cached_manifest
    from services.customer_reply_v2.retrieval_tools import ToolContext, dispatch_retrieval_tool

    rev, _ = get_cached_manifest("t_big")
    ctx = ToolContext(tenant_id="t_big", published_revision=rev, channel="instagram_dm")
    monkeypatch.setattr("services.customer_reply_v2.retrieval_tools.record_content", lambda *_a, **_k: "x" * 12001)
    out = dispatch_retrieval_tool("read_published_cm_items", {"item_ids": ["knowledge:kn_hours"]}, ctx)
    assert out["data"]["silent_truncation"] is False
    assert out["data"]["evidence"] == []
    assert out["data"]["rejected"][0]["reason"] == "file_too_large"


@pytest.mark.asyncio
async def test_luna_scripted_plan_records_recommended_tera_effort(v2_env):
    await publish_test_content("t_effort", _rich_sections())
    from services.customer_reply_v2.retrieval_luna import run_retrieval_luna

    result = await run_retrieval_luna(
        tenant_id="t_effort",
        message="hi",
        customer_profile={},
        scripted_tool_calls=[
            {
                "final_plan": {
                    "evidence_status": "sufficient",
                    "selected_source_ids": [],
                    "recommended_tera_effort": "low",
                }
            }
        ],
    )
    assert result.requested_reasoning_effort == "low"
    assert result.recommended_tera_effort == "low"

    invalid = await run_retrieval_luna(
        tenant_id="t_effort",
        message="hi",
        customer_profile={},
        scripted_tool_calls=[
            {
                "final_plan": {
                    "evidence_status": "sufficient",
                    "selected_source_ids": [],
                    "recommended_tera_effort": "high",
                }
            }
        ],
    )
    assert invalid.recommended_tera_effort == "medium"


@pytest.mark.asyncio
async def test_tera_payload_has_merged_profile(v2_env):
    await publish_test_content("t_profile", _rich_sections())
    from services.customer_reply_v2.ai_profile import load_tera_ai_context
    from services.customer_reply_v2.answer_luna import answer_context_has_full_basics_and_style, build_answer_messages

    fixed = load_tera_ai_context("t_profile")
    assert "ai_profile" in fixed
    msgs = build_answer_messages(
        message="hi",
        fixed_context=fixed,
        evidence=[],
        evidence_status="sufficient",
        customer_profile={},
        history_messages=[],
        comment_context=None,
        channel="instagram_dm",
        published_revision="v",
        response_language="en",
        detected_language="en",
    )
    blob = str(msgs)
    assert "ai_profile" in blob
    assert answer_context_has_full_basics_and_style(msgs)


@pytest.mark.asyncio
async def test_luna_manifest_excludes_ai_basics_bodies(v2_env):
    await publish_test_content("t_luna_titles", _rich_sections())
    from services.cm.version_store import load_published_content
    from services.customer_reply_v2.manifest import manifest_for_retrieval_luna
    from services.customer_reply_v2.operational_titles import collect_operational_titles, inline_titles_for_luna

    data = manifest_for_retrieval_luna("t_luna_titles")
    blob = str(data) + str(
        inline_titles_for_luna(collect_operational_titles(load_published_content("t_luna_titles")[1]))
    )
    assert "advanced_instructions" not in blob
    assert "style_body" not in blob
