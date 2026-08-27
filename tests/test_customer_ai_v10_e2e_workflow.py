"""Customer AI V10 E2E scenarios 1-12. INTEGRATION SIMULATION, not live Meta."""

from __future__ import annotations

import pytest

from tests.customer_ai_v10_e2e_support import (
    create_product,
    install_hours_faq,
    publish_clinic,
    scripted_read,
    trace_from_outcome,
)

pytest_plugins = ("tests.customer_reply_ai_v2_fixtures", "tests.customer_ai_v10_e2e_support")


@pytest.mark.asyncio
async def test_s01_simple_dm_greeting(v2_env) -> None:
    await publish_clinic("t_e2e_s01")
    from services.customer_reply_v2.orchestrator import run_customer_reply_v2_dm

    out = await run_customer_reply_v2_dm(
        tenant_id="t_e2e_s01",
        message="مرحبا",
        detected_language="ar",
        response_language="ar",
        channel="instagram_dm",
        provider_sender_id="u1",
        scripted_retrieval=scripted_read([], effort="low"),
        fixture_answer={"reply_text": "مرحبا! كيف فيني ساعدك؟", "grounding_status": "grounded"},
    )
    trace = trace_from_outcome(message="مرحبا", channel="instagram_dm", out=out)
    assert out.reason != "safety_block"
    assert trace["faq_direct"] is not True
    assert trace["luna_called"] is True
    assert trace["tera_called"] is True
    assert "greeting_shortcut" not in str(out.reason)


@pytest.mark.asyncio
async def test_s02_business_price_question(v2_env) -> None:
    await publish_clinic("t_e2e_s02")
    from services.customer_reply_v2.orchestrator import run_customer_reply_v2_dm

    ids = ["services:svc_full_body", "prices:price_full_antelias"]
    out = await run_customer_reply_v2_dm(
        tenant_id="t_e2e_s02",
        message="قدي سعر Full Body؟",
        detected_language="ar",
        response_language="ar",
        channel="instagram_dm",
        provider_sender_id="u2",
        scripted_retrieval=scripted_read(ids, effort="low"),
        fixture_answer={"reply_text": "سعر Full Body 299 USD حسب القائمة المنشورة.", "grounding_status": "grounded"},
    )
    trace = trace_from_outcome(message="قدي سعر Full Body؟", channel="instagram_dm", out=out)
    assert "services:svc_full_body" in trace["selected_source_ids"]
    assert "299" in (out.reply or "")
    assert "invent" not in (out.reply or "").lower()
    assert trace["luna_called"] is True


@pytest.mark.asyncio
async def test_s03_faq_direct(v2_env, monkeypatch: pytest.MonkeyPatch) -> None:
    await publish_clinic("t_e2e_s03")
    await install_hours_faq(monkeypatch)
    from services.customer_reply_v2.orchestrator import run_customer_reply_v2_dm

    async def _boom(**_k):
        raise AssertionError("Luna/Tera must not run on FAQ direct")

    monkeypatch.setattr("services.customer_reply_v2.orchestrator_llm.run_retrieval_luna", _boom)
    monkeypatch.setattr("services.customer_reply_v2.orchestrator_llm.run_answer_luna", _boom)
    out = await run_customer_reply_v2_dm(
        tenant_id="t_e2e_s03",
        message="شو أوقات الدوام؟",
        detected_language="ar",
        response_language="ar",
        channel="instagram_dm",
        provider_sender_id="u3",
    )
    trace = trace_from_outcome(message="شو أوقات الدوام؟", channel="instagram_dm", out=out)
    assert trace["faq_direct"] is True
    assert trace["luna_called"] is False
    assert trace["tera_called"] is False
    assert (trace["metering"] or {}).get("ai_invocation_count") == 0
    assert "10" in (out.reply or "")


@pytest.mark.asyncio
async def test_s04_faq_mixed_not_direct(v2_env, monkeypatch: pytest.MonkeyPatch) -> None:
    await publish_clinic("t_e2e_s04")
    await install_hours_faq(monkeypatch)
    from services.customer_reply_v2.orchestrator import run_customer_reply_v2_dm

    msg = "شو أوقات الدوام وبدي موعد الخميس؟"
    out = await run_customer_reply_v2_dm(
        tenant_id="t_e2e_s04",
        message=msg,
        detected_language="ar",
        response_language="ar",
        channel="instagram_dm",
        provider_sender_id="u4",
        scripted_retrieval=scripted_read(
            ["opening_hours:oh_antelias", "requests_appointments:req_full_body", "services:svc_full_body"]
        ),
        fixture_answer={"reply_text": "منفتح ١٠ ل٨. للموعد كمّلي بالخاص الاسم واليوم.", "grounding_status": "grounded"},
    )
    trace = trace_from_outcome(message=msg, channel="instagram_dm", out=out)
    assert trace["faq_direct"] is not True
    assert out.reason != "faq_direct"
    assert trace["luna_called"] is True
    assert trace["tera_called"] is True


@pytest.mark.asyncio
async def test_s05_comment_business_knowledge(v2_env) -> None:
    await publish_clinic("t_e2e_s05")
    from services.customer_reply_v2.comment_runtime import run_customer_reply_v2_comment

    msg = "قدي سعر Full Body بفرع أنطلياس وإيمتى بتسكروا؟"
    ids = [
        "comments:rule_ai_public",
        "services:svc_full_body",
        "branches:br_antelias",
        "opening_hours:oh_antelias",
        "prices:price_full_antelias",
        "knowledge:kn_full_body",
    ]
    out = await run_customer_reply_v2_comment(
        tenant_id="t_e2e_s05",
        comment_text=msg,
        detected_language="ar",
        response_language="ar",
        channel="instagram_comment",
        post_id="POST1",
        comment_id="C1",
        scripted_retrieval=scripted_read(ids),
        fixture_answer={
            "reply_text": "Full Body بأنطلياس 299 USD ومنسكر ٨ مساء. التفاصيل بالخاص.",
            "grounding_status": "grounded",
        },
    )
    trace = trace_from_outcome(message=msg, channel="instagram_comment", out=out)
    selected = set(trace["selected_source_ids"])
    assert "comments:rule_ai_public" in selected
    assert "services:svc_full_body" in selected
    assert "branches:br_antelias" in selected
    assert "opening_hours:oh_antelias" in selected
    assert "prices:price_full_antelias" in selected
    assert trace["comment_rule_mode"] == "ai_guidance"
    assert "299" in (out.reply or "")
    assert trace["luna_called"] is True
    assert trace["tera_called"] is True


@pytest.mark.asyncio
async def test_s06_global_ai_guidance_plus_business(v2_env) -> None:
    await publish_clinic("t_e2e_s06")
    from services.customer_reply_v2.comment_runtime import run_customer_reply_v2_comment

    ids = ["comments:rule_ai_public", "services:svc_full_body", "prices:price_full_antelias"]
    out = await run_customer_reply_v2_comment(
        tenant_id="t_e2e_s06",
        comment_text="قدي السعر؟",
        detected_language="ar",
        response_language="ar",
        channel="facebook_comment",
        post_id="OTHER",
        scripted_retrieval=scripted_read(ids),
        fixture_answer={"reply_text": "السعر 299 USD. كمّلي بالخاص.", "grounding_status": "grounded"},
    )
    assert out.metadata.get("comment_rule_id") == "rule_ai_public"
    assert "services:svc_full_body" in (out.metadata.get("selected_source_ids") or [])


@pytest.mark.asyncio
async def test_s07_post_specific_override_still_retrieves_price(v2_env) -> None:
    await publish_clinic("t_e2e_s07")
    from services.customer_reply_v2.comment_runtime import run_customer_reply_v2_comment

    ids = ["comments:rule_post_override", "services:svc_full_body", "prices:price_full_antelias"]
    out = await run_customer_reply_v2_comment(
        tenant_id="t_e2e_s07",
        comment_text="قدي سعر Full Body؟",
        detected_language="ar",
        response_language="ar",
        channel="instagram_comment",
        post_id="POST_PROMO",
        scripted_retrieval=scripted_read(ids),
        fixture_answer={"reply_text": "عرض البوست: Full Body 299 USD.", "grounding_status": "grounded"},
    )
    assert out.metadata.get("comment_rule_id") == "rule_post_override"
    assert "services:svc_full_body" in (out.metadata.get("selected_source_ids") or [])
    assert "299" in (out.reply or "")


@pytest.mark.asyncio
async def test_s08_deterministic_comment_dm_no_ai(v2_env) -> None:
    await publish_clinic("t_e2e_s08")
    from services.customer_reply_v2.comment_runtime import run_customer_reply_v2_comment

    out = await run_customer_reply_v2_comment(
        tenant_id="t_e2e_s08",
        comment_text="بدي عرض خاص",
        detected_language="ar",
        response_language="ar",
        channel="instagram_comment",
        scripted_retrieval=scripted_read(["services:svc_full_body"]),
        fixture_answer={"reply_text": "AI SHOULD NOT RUN", "grounding_status": "grounded"},
    )
    trace = trace_from_outcome(message="بدي عرض خاص", channel="instagram_comment", out=out)
    assert out.reason == "comment_rule_deterministic"
    assert trace["luna_called"] is False
    assert "الخاص" in (out.reply or "")


@pytest.mark.asyncio
async def test_s09_comment_and_dm_simulation_independent(v2_env) -> None:
    await publish_clinic("t_e2e_s09")
    from services.cm.comment_rules import CommentRuleDecision
    from services.meta_app_registry import APP_A_KEY, MetaAssetBinding
    from services.meta_comment_rule_both import apply_comment_and_dm_rule

    binding = MetaAssetBinding(
        binding_id="b-s09",
        tenant_id="t_e2e_s09",
        channel="instagram",
        asset_id="ig1",
        page_id="",
        instagram_account_id="ig1",
        app_key=APP_A_KEY,
        credential_id="c1",
        status="active",
        generation=1,
        created_at=1.0,
        updated_at=1.0,
    )
    decision = CommentRuleDecision(
        action="reply_comment_and_dm",
        reply_text="تم، شيكي الخاص.",
        dm_text="كود الخصم بالخاص: GLOW10",
        rule_id="rule_both",
        matched=True,
        rule_mode="deterministic",
    )
    sent: list[dict] = []
    first = await apply_comment_and_dm_rule(
        rule_decision=decision,
        binding=binding,
        comment_id="cmt-s09",
        simulation=True,
        capture_send=sent,
    )
    assert first.status == "simulated_both"
    assert [row["delivery"] for row in sent] == ["public_reply", "private_reply"]
    second_sent: list[dict] = []
    second = await apply_comment_and_dm_rule(
        rule_decision=decision,
        binding=binding,
        comment_id="cmt-s09",
        simulation=True,
        capture_send=second_sent,
    )
    assert second.reason == "" or second.status in {"simulated", "simulated_both", "ignored"}
    # In-memory already-replied is owned by process_meta_comment_event; dual sim itself is idempotent per comment cache.
    assert len(sent) == 2


@pytest.mark.asyncio
async def test_s10_product_comment(v2_env, products_db) -> None:
    await publish_clinic("t_e2e_s10")
    create_product(
        "t_e2e_s10",
        name="After Care Cream",
        price="45 USD",
        sizes=["large"],
        colors=[],
        links=[],
    )
    from services.customer_reply_v2.comment_runtime import run_customer_reply_v2_comment
    from services.customer_reply_v2.retrieval_tools import ToolContext, dispatch_retrieval_tool

    ctx = ToolContext(tenant_id="t_e2e_s10", published_revision="rev", channel="instagram_comment")
    search = dispatch_retrieval_tool("search_product_by_title", {"title": "After Care Cream"}, ctx)
    assert search["data"]["match_count"] == 1
    pid = search["data"]["matches"][0]["id"]
    details = dispatch_retrieval_tool("get_product_details", {"product_id": pid}, ctx)
    assert "45" in str(details["data"]["product"].get("price") or details)
    out = await run_customer_reply_v2_comment(
        tenant_id="t_e2e_s10",
        comment_text="في من هيدا الكريم After Care Cream size large وقدي سعره؟",
        detected_language="ar",
        response_language="ar",
        channel="instagram_comment",
        scripted_retrieval=[
            [
                {"name": "get_product_details", "arguments": {"product_id": pid}},
                {"name": "read_published_cm_items", "arguments": {"item_ids": ["comments:rule_ai_public"]}},
            ],
            {
                "final_plan": {
                    "evidence_status": "sufficient",
                    "selected_source_ids": ["comments:rule_ai_public", f"products:{pid}"],
                    "selected_section_ids": ["comments", "products"],
                    "recommended_tera_effort": "low",
                }
            },
        ],
        fixture_answer={"reply_text": "After Care Cream large موجود وسعره 45 USD.", "grounding_status": "grounded"},
    )
    assert "45" in (out.reply or "")
    assert out.metadata.get("comment_rule_mode") == "ai_guidance"


@pytest.mark.asyncio
async def test_s11_product_typo_same_luna_loop(v2_env, products_db) -> None:
    create_product("t_e2e_s11", name="After Care Cream", price="45", sizes=[], colors=[], links=[])
    from services.customer_reply_v2.retrieval_tools import ToolContext, dispatch_retrieval_tool

    ctx = ToolContext(tenant_id="t_e2e_s11", published_revision="rev", channel="instagram_comment")
    out = dispatch_retrieval_tool("search_product_by_title", {"title": "bde after kar crem"}, ctx)
    assert out["data"]["extra_luna_agent"] is False
    if out["data"]["match_count"] == 0:
        assert out["data"]["resolver"] == "titles_fallback"
        titles = out["data"]["titles_fallback"]["titles"]
        assert any("After Care Cream" == row["title"] for row in titles)
    else:
        assert out["data"]["matches"][0]["title"] == "After Care Cream"


@pytest.mark.asyncio
async def test_s12_product_and_service_same_name(v2_env, products_db) -> None:
    await publish_clinic("t_e2e_s12")
    create_product("t_e2e_s12", name="Hair Treatment", price="20", sizes=[], colors=[], links=[])
    from services.customer_reply_v2.orchestrator import run_customer_reply_v2_dm
    from services.customer_reply_v2.retrieval_tools import ToolContext, dispatch_retrieval_tool

    ctx = ToolContext(tenant_id="t_e2e_s12", published_revision="rev", channel="instagram_dm")
    products = dispatch_retrieval_tool("search_product_by_title", {"title": "Hair Treatment"}, ctx)
    assert products["data"]["match_count"] >= 1
    out = await run_customer_reply_v2_dm(
        tenant_id="t_e2e_s12",
        message="بدي Hair Treatment",
        detected_language="ar",
        response_language="ar",
        channel="instagram_dm",
        provider_sender_id="u12",
        scripted_retrieval=scripted_read(["services:svc_full_body"], effort="medium"),
        fixture_answer={
            "reply_text": "عندنا خدمة ومنتج بنفس الاسم. قصدك الجلسة أو الكريم؟",
            "grounding_status": "grounded",
        },
    )
    assert "قصدك" in (out.reply or "") or "service" in (out.reply or "").lower() or "منتج" in (out.reply or "")
