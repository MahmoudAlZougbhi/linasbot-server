"""Customer Reply AI V2 — retrieval/orchestrator integration fixtures."""

from __future__ import annotations

import pytest

from tests.cm_test_helpers import publish_test_content
from tests.customer_reply_ai_v2_helpers import _rich_sections

pytest_plugins = ("tests.customer_reply_ai_v2_fixtures",)


@pytest.mark.asyncio
async def test_faq_fast_path_and_context_dependent(v2_env, monkeypatch):
    await publish_test_content("t_faq", _rich_sections())
    from services.customer_reply_v2.faq_fast_path import is_context_dependent_question, try_faq_fast_path

    assert is_context_dependent_question("قديش هيدا؟") is True

    async def _fake_tier(message, lang):
        if "hours" in message.lower() or "أوقات" in message:
            return {"tier": "exact", "match_score": 1.0, "qa_pair": {"answer": "We open 10am to 6pm."}}
        return None

    monkeypatch.setattr(
        "services.local_qa_service.local_qa_service.find_match_with_tier",
        _fake_tier,
    )
    hit = await try_faq_fast_path(tenant_id="t_faq", message="What are your hours?", detected_language="en")
    assert hit.hit is True
    miss = await try_faq_fast_path(tenant_id="t_faq", message="قديش هيدا؟", detected_language="ar")
    assert miss.hit is False
    assert miss.reason == "context_dependent"


@pytest.mark.asyncio
async def test_retrieval_round_limit_and_role_separation(v2_env):
    await publish_test_content("t_ret", _rich_sections())
    from services.customer_reply_v2.answer_luna import answer_context_has_full_basics_and_style, build_answer_messages
    from services.customer_reply_v2.manifest import load_fixed_answer_context
    from services.customer_reply_v2.models import EvidenceRecord
    from services.customer_reply_v2.retrieval_luna import run_retrieval_luna
    from services.customer_reply_v2.retrieval_tools import ToolContext, dispatch_retrieval_tool

    # Round 3 refused server-side
    ctx = ToolContext(tenant_id="t_ret", published_revision="v_t_ret", channel="instagram_dm", round_index=2)
    refused = dispatch_retrieval_tool(
        "request_additional_published_cm_items",
        {"item_ids": ["services:svc_full"], "reason": "need more"},
        ctx,
    )
    assert refused["ok"] is False
    assert refused["error"] == "retrieval_round_limit"
    assert ctx.refused_third_round is True

    result = await run_retrieval_luna(
        tenant_id="t_ret",
        message="ade se3er full bdy lal women b beirut?",
        customer_profile={"effective_name": "Sara"},
        scripted_tool_calls=[
            [
                {"name": "list_published_cm_sections", "arguments": {}},
                {"name": "list_published_cm_items", "arguments": {"section_ids": ["services", "prices", "branches"]}},
                {
                    "name": "read_published_cm_items",
                    "arguments": {"item_ids": ["services:svc_full", "prices:price_full_w", "branches:br_beirut"]},
                },
            ],
            {
                "final_plan": {
                    "evidence_status": "sufficient",
                    "selected_source_ids": ["services:svc_full"],
                    "selected_section_ids": ["services", "prices", "branches"],
                }
            },
        ],
    )
    assert result.requested_model == "gpt-5.6-luna"
    assert result.returned_model == "gpt-5.6-luna"
    assert result.evidence_status == "sufficient"
    assert len(result.evidence) >= 1
    # Not fixed top-2 knowledge/care — Luna selected services/prices/branches
    assert "services" in result.selected_section_ids or any(e.section_id == "services" for e in result.evidence)

    # Attempt third round via scripted path
    result2 = await run_retrieval_luna(
        tenant_id="t_ret",
        message="more?",
        customer_profile={},
        scripted_tool_calls=[
            [{"name": "list_published_cm_items", "arguments": {"section_ids": ["care"]}}],
            [
                {
                    "name": "request_additional_published_cm_items",
                    "arguments": {"section_ids": ["knowledge"], "item_ids": ["knowledge:kn_hours"]},
                }
            ],
            [{"name": "request_additional_published_cm_items", "arguments": {"item_ids": ["care:care_pre"]}}],
            {"final_plan": {"evidence_status": "insufficient_can_retry", "selected_source_ids": []}},
        ],
    )
    assert result2.refused_third_round is True
    assert result2.evidence_status == "insufficient_final"

    fixed = load_fixed_answer_context("t_ret")
    assert fixed["ai_basics"].get("advanced_instructions")
    assert fixed["style"].get("style_body")
    msgs = build_answer_messages(
        message="hi",
        fixed_context=fixed,
        evidence=[EvidenceRecord("services:svc_full", "services", "Full", "Full body", "v_t_ret")],
        evidence_status="sufficient",
        customer_profile={"effective_name": "Sara"},
        history_messages=[],
        comment_context=None,
        channel="instagram_dm",
        published_revision="v_t_ret",
        response_language="en",
        detected_language="en",
    )
    assert answer_context_has_full_basics_and_style(msgs)
    # Answer Luna has no tools in call path — verified by run_answer_luna raising if tools passed


@pytest.mark.asyncio
async def test_multi_intent_and_insufficient_and_languages(v2_env):
    await publish_test_content("t_multi", _rich_sections())
    from services.customer_reply_v2.orchestrator import run_customer_reply_v2_dm

    questions = [
        ("ade se3er full bdy lal women b beirut?", "en"),
        ("Do you have this service in the other branch and are you open tomorrow?", "en"),
        ("شو لازم أعمل قبل الجلسة وبعدها؟", "ar"),
        ("je veux connaître le prix et l’adresse de la branche.", "fr"),
    ]
    for q, lang in questions:
        out = await run_customer_reply_v2_dm(
            tenant_id="t_multi",
            message=q,
            detected_language=lang,
            response_language=lang if lang != "franco" else "ar",
            channel="instagram_dm",
            provider_sender_id="u_multi",
            provider_display_name="Test User",
            scripted_retrieval=[
                [
                    {
                        "name": "list_published_cm_items",
                        "arguments": {
                            "section_ids": ["services", "prices", "branches", "care", "knowledge", "off_days"]
                        },
                    },
                    {
                        "name": "read_published_cm_items",
                        "arguments": {
                            "item_ids": [
                                "services:svc_full",
                                "prices:price_full_w",
                                "branches:br_beirut",
                                "branches:br_other",
                                "care:care_pre",
                                "care:care_post",
                                "knowledge:kn_hours",
                            ]
                        },
                    },
                ],
                {
                    "final_plan": {
                        "evidence_status": "sufficient",
                        "selected_section_ids": ["services", "prices", "branches", "care", "knowledge"],
                        "selected_source_ids": ["services:svc_full", "prices:price_full_w"],
                        "multi_intent": True,
                    }
                },
            ],
            fixture_answer={
                "reply_text": f"Answer for: {q[:40]}",
                "detected_language": lang,
                "grounding_status": "grounded",
                "evidence_source_ids": ["services:svc_full"],
            },
        )
        assert out.reply
        assert out.metadata.get("authoritative_selector") == "retrieval_luna"
        assert out.metadata.get("requested_model_retrieval") == "gpt-5.6-luna"
        assert out.metadata.get("requested_model_answer") == "gpt-5.6-terra"

    # Insufficient final — honest answer
    out_miss = await run_customer_reply_v2_dm(
        tenant_id="t_multi",
        message="Do you sell spaceships?",
        detected_language="en",
        response_language="en",
        provider_sender_id="u_miss",
        scripted_retrieval=[
            [{"name": "list_published_cm_items", "arguments": {"section_ids": ["services"]}}],
            {"final_plan": {"evidence_status": "insufficient_final", "selected_source_ids": []}},
        ],
        fixture_answer={
            "reply_text": "",
            "grounding_status": "insufficient",
            "safe_failure_category": "not_in_published_cm",
        },
    )
    assert out_miss.reply
    assert "couldn't confirm" in out_miss.reply.lower() or "published" in out_miss.reply.lower()


@pytest.mark.asyncio
async def test_validation_failure_never_sends_invalid(v2_env, monkeypatch):
    await publish_test_content("t_val", _rich_sections())
    from services.customer_reply_v2 import orchestrator as orch

    calls = {"n": 0}

    def _fake_validate(*, tenant_id, candidate, retrieval, detected_language, response_language):
        calls["n"] += 1
        if "INVENTED_PRICE_99999" in candidate:
            return False, ["price_not_in_evidence"]
        return True, []

    monkeypatch.setattr(orch, "_validate_candidate", _fake_validate)
    out = await orch.run_customer_reply_v2_dm(
        tenant_id="t_val",
        message="price?",
        detected_language="en",
        response_language="en",
        provider_sender_id="u_val",
        scripted_retrieval=[
            [
                {
                    "name": "read_published_cm_items",
                    "arguments": {"item_ids": ["prices:price_full_w"]},
                }
            ],
            {"final_plan": {"evidence_status": "sufficient", "selected_source_ids": ["prices:price_full_w"]}},
        ],
        fixture_answer={
            "reply_text": "It costs INVENTED_PRICE_99999 USD",
            "repair_reply_text": "It costs INVENTED_PRICE_99999 USD",
            "grounding_status": "grounded",
            "evidence_source_ids": ["prices:price_full_w"],
        },
    )
    assert "99999" not in (out.reply or "")
    assert calls["n"] >= 2


@pytest.mark.asyncio
async def test_comment_toggle_media_and_no_dm_mix(v2_env):
    await publish_test_content("t_cmt", _rich_sections())
    from services.customer_reply_v2.media_context import seed_video_cache_for_tests
    from services.customer_reply_v2.orchestrator import run_customer_reply_v2_comment

    off = await run_customer_reply_v2_comment(
        tenant_id="t_cmt",
        comment_text="Nice!",
        comments_enabled=False,
    )
    assert off.reason == "comments_toggle_off"
    assert off.reply is None

    seed_video_cache_for_tests(
        tenant_id="t_cmt",
        media_revision="media_vid_1",
        caption="Summer promo reel",
        visual_summary="Person smiling near clinic sign; no price visible.",
        frame_urls=["https://example.invalid/f1.jpg", "https://example.invalid/f2.jpg"],
    )
    out = await run_customer_reply_v2_comment(
        tenant_id="t_cmt",
        comment_text="شو هيدا بالفيديو؟",
        channel="instagram_comment",
        caption="Summer promo reel",
        media_type="video",
        media_id="media_vid_1",
        parent_comment="",
        scripted_retrieval=[
            [
                {"name": "get_comment_post_context", "arguments": {}},
                {"name": "list_published_cm_items", "arguments": {"section_ids": ["knowledge"]}},
            ],
            {"final_plan": {"evidence_status": "sufficient", "selected_source_ids": ["knowledge:kn_hours"]}},
        ],
        fixture_answer={
            "reply_text": "هيدا ريل عن العيادة — للتفاصيل ابعتلنا خاص.",
            "grounding_status": "grounded",
        },
        injected_media_cache={
            "media_type": "video",
            "caption": "Summer promo reel",
            "visual_summary": "Person smiling near clinic sign; no price visible.",
            "frame_urls": ["https://example.invalid/f1.jpg"],
            "frame_count": 1,
        },
    )
    assert out.reply
    assert out.metadata.get("dm_history_mixed") is False
    assert out.metadata["comment_context"]["media_type"] == "video"
    assert out.metadata["comment_context"]["cached_visual_summary"]


@pytest.mark.asyncio
async def test_tenant_isolation_draft_and_path_rejection(v2_env):
    await publish_test_content("t_a", _rich_sections())
    await publish_test_content("t_b", _rich_sections())
    from services.cm.version_store import read_published_pointer
    from services.customer_reply_v2.retrieval_tools import ToolContext, dispatch_retrieval_tool

    pointer = read_published_pointer("t_a")
    assert pointer
    ctx = ToolContext(tenant_id="t_a", published_revision=pointer.content_version_id, channel="instagram_dm")
    bad = dispatch_retrieval_tool(
        "read_published_cm_items",
        {"item_ids": ["../../etc/passwd", "https://evil.example/x", "services:svc_full"]},
        ctx,
    )
    rejected = set(bad["data"]["rejected_item_ids"])
    assert "../../etc/passwd" in rejected
    assert "https://evil.example/x" in rejected
    assert any(e["source_id"].endswith("svc_full") for e in bad["data"]["evidence"])

    # Stale revision rejected
    stale = ToolContext(tenant_id="t_a", published_revision="stale_rev", channel="instagram_dm")
    with pytest.raises(ValueError, match="stale"):
        dispatch_retrieval_tool("list_published_cm_items", {"section_ids": ["services"]}, stale)
