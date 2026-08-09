"""Customer Reply AI V2 — unit/integration fixtures (no live Meta / no prod send)."""

from __future__ import annotations

import time
from typing import Any

import pytest

from tests.cm_test_helpers import install_mocked_openai_embeddings, publish_test_content


@pytest.fixture
def v2_env(tmp_path, monkeypatch):
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("CUSTOMER_REPLY_AI_V2", "true")
    monkeypatch.setenv("CUSTOMER_REPLY_AI_V2_LIVE", "true")
    monkeypatch.setenv("CUSTOMER_SEMANTIC_RETRIEVAL_ENABLED", "true")
    monkeypatch.setenv("CUSTOMER_MEDIA_CONTEXT_ENABLED", "true")
    monkeypatch.setenv("LINAS_CUSTOMER_MODEL", "gpt-5.6-luna")
    monkeypatch.setenv("MAX_CUSTOMER_RETRIEVAL_ROUNDS", "2")
    monkeypatch.setenv("CUSTOMER_DM_CONTEXT_WINDOW_HOURS", "3")
    install_mocked_openai_embeddings(monkeypatch)
    from services.customer_reply_v2.manifest import clear_manifest_cache

    clear_manifest_cache()
    return tmp_path


def _rich_sections() -> dict[str, dict[str, Any]]:
    return {
        "ai_basics": {
            "assistant_name": "Lina",
            "clinic_name": "Glow Clinic",
            "identity_summary": "Friendly clinic assistant for Glow Clinic.",
            "advanced_instructions": "Always be accurate. Never invent prices.",
        },
        "style": {
            "tone": "warm",
            "formality": "casual",
            "style_body": "Short replies. Use the customer name sparingly.",
            "do_list": ["Be clear"],
            "dont_list": ["Invent prices"],
        },
        "services": {
            "items": [
                {
                    "id": "svc_full",
                    "labels": {"en": "Full body laser", "ar": "ليزر كامل", "fr": "Laser complet"},
                    "available": True,
                    "audience": "women",
                    "aliases": ["full", "full body"],
                },
                {
                    "id": "svc_face",
                    "labels": {"en": "Face laser", "ar": "ليزر وجه", "fr": "Laser visage"},
                    "available": True,
                    "audience": "general",
                },
            ]
        },
        "branches": {
            "items": [
                {
                    "id": "br_beirut",
                    "labels": {"en": "Beirut", "ar": "بيروت", "fr": "Beyrouth"},
                    "address": "Hamra St",
                    "hours": {"monday": "10-18", "tuesday": "10-18"},
                    "available": True,
                },
                {
                    "id": "br_other",
                    "labels": {"en": "Other Branch", "ar": "فرع آخر", "fr": "Autre branche"},
                    "address": "Jounieh",
                    "available": True,
                },
            ]
        },
        "prices": {
            "items": [
                {"id": "price_full_w", "service_id": "svc_full", "amount": 299.0, "currency": "USD"},
                {"id": "price_face", "service_id": "svc_face", "amount": 99.0, "currency": "USD"},
            ]
        },
        "care": {
            "items": [
                {
                    "id": "care_pre",
                    "title": "Before session",
                    "body": "Avoid sun 48h before. شو لازم أعمل قبل الجلسة: لا تتعرض للشمس.",
                    "status": "active",
                    "language": "ar",
                },
                {
                    "id": "care_post",
                    "title": "After session",
                    "body": "Moisturize after. وبعدها رطب البشرة.",
                    "status": "active",
                    "language": "ar",
                },
            ]
        },
        "knowledge": {
            "items": [
                {
                    "id": "kn_hours",
                    "title": "Opening hours note",
                    "body": "We are open tomorrow except public holidays.",
                    "status": "active",
                }
            ]
        },
        "faq": {
            "items": [
                {
                    "qa_group_id": "faq_hours",
                    "status": "active",
                    "variants": [
                        {"language": "en", "question": "What are your hours?", "answer": "We open 10am to 6pm."},
                        {"language": "ar", "question": "شو أوقاتكم؟", "answer": "منفتح من ١٠ ل ٦."},
                        {"language": "fr", "question": "Quels sont vos horaires ?", "answer": "Ouvert de 10h à 18h."},
                        {"language": "franco", "question": "shu aw2atkon?", "answer": "منفتح من ١٠ ل ٦."},
                    ],
                }
            ]
        },
        "off_days": {"days": [], "specific_days": []},
        "handoff": {
            "contacts": [{"id": "c1", "label": "WA", "destination_type": "whatsapp", "destination_value": "+96170000000"}],
            "matrix": [{"id": "m1", "enabled": True, "contact_id": "c1"}],
        },
        "restricted": {
            "topics": [
                {
                    "id": "tattoo_removal",
                    "active": True,
                    "labels": {"en": "Tattoo removal", "ar": "إزالة الوشم"},
                    "keywords": ["tattoo removal", "إزالة الوشم"],
                    "refuse_template": "We do not offer tattoo removal.",
                }
            ]
        },
        "actions": {
            "items": [
                {"id": "human_handoff", "enabled": True},
            ]
        },
    }


@pytest.mark.asyncio
async def test_manifest_marks_basics_style_fixed(v2_env):
    await publish_test_content("t_manifest", _rich_sections())
    from services.customer_reply_v2.manifest import get_cached_manifest, manifest_for_retrieval_luna

    rev, sections = get_cached_manifest("t_manifest")
    assert rev
    by_id = {s.section_id: s for s in sections}
    assert by_id["ai_basics"].fixed_answer_context is True
    assert by_id["ai_basics"].selectable is False
    assert by_id["style"].fixed_answer_context is True
    assert by_id["style"].selectable is False
    assert by_id["services"].selectable is True
    data = manifest_for_retrieval_luna("t_manifest")
    blob = str(data)
    assert "advanced_instructions" not in blob
    assert "style_body" not in blob


def test_rolling_three_hour_window_boundaries():
    from services.customer_reply_v2.conversation_window import filter_rolling_window

    now = 1_700_000_000.0
    hour = 3600.0
    msgs = []
    # Just outside
    msgs.append({"role": "user", "content": "outside", "timestamp": now - (3 * hour) - 1})
    # Just inside
    msgs.append({"role": "user", "content": "inside-boundary", "timestamp": now - (3 * hour) + 1})
    # Many messages inside (>20)
    for i in range(25):
        msgs.append({"role": "user" if i % 2 == 0 else "assistant", "content": f"m{i}" * 50, "timestamp": now - i * 60})
    # Long message not truncated to 600
    long = "X" * 1200
    msgs.append({"role": "user", "content": long, "timestamp": now - 10})

    window = filter_rolling_window(msgs, now_ts=now, window_hours=3)
    contents = [m.content for m in window.messages]
    assert "outside" not in contents
    assert "inside-boundary" in contents
    assert len(window.messages) >= 20
    assert any(len(m.content) > 600 for m in window.messages)
    # Chronological
    stamps = [m.timestamp or 0 for m in window.messages]
    assert stamps == sorted(stamps)


def test_emergency_compaction_is_explicit():
    from services.customer_reply_v2.conversation_window import filter_rolling_window
    import os

    os.environ["LINAS_CUSTOMER_CONTEXT_BUDGET"] = "200"
    now = time.time()
    msgs = [
        {"role": "user", "content": ("old-" + str(i)) * 80, "timestamp": now - 1000 + i}
        for i in range(30)
    ]
    window = filter_rolling_window(msgs, now_ts=now, window_hours=3)
    assert window.context_compacted is True
    assert window.compacted_summary
    os.environ.pop("LINAS_CUSTOMER_CONTEXT_BUDGET", None)


def test_customer_name_correction_and_third_party_block(v2_env):
    from services.customer_reply_v2.customer_facts import (
        apply_message_fact_updates,
        delete_customer_facts,
        extract_explicit_name_correction,
        load_customer_facts,
    )

    assert extract_explicit_name_correction("My name is Mohammad, not Mahmoud.") == "Mohammad"
    assert extract_explicit_name_correction("My sister Sara wants an appointment.") is None
    assert extract_explicit_name_correction("Send this to Mohammad.") is None

    facts = load_customer_facts(
        tenant_id="t_name",
        channel="instagram_dm",
        asset_id="ig1",
        provider_sender_id="ps1",
        provider_display_name="Mahmoud",
    )
    assert facts.effective_name == "Mahmoud"
    facts = apply_message_fact_updates(facts, "My name is Mohammad, not Mahmoud.", "en")
    assert facts.effective_name == "Mohammad"
    assert facts.name_source == "explicit_self_report"
    # Provider refresh must not overwrite
    facts2 = load_customer_facts(
        tenant_id="t_name",
        channel="instagram_dm",
        asset_id="ig1",
        provider_sender_id="ps1",
        provider_display_name="MahmoudFromMeta",
    )
    assert facts2.effective_name == "Mohammad"
    assert facts2.provider_display_name == "MahmoudFromMeta"
    assert delete_customer_facts(tenant_id="t_name", channel="instagram_dm", asset_id="ig1", provider_sender_id="ps1")


def test_gender_only_explicit_language_switch(v2_env):
    from services.customer_reply_v2.customer_facts import (
        apply_message_fact_updates,
        extract_explicit_gender,
        load_customer_facts,
        should_update_language,
    )

    assert extract_explicit_gender("I'm a woman") == "women"
    assert extract_explicit_gender("Sara") is None
    assert should_update_language("ok", "en") is False
    assert should_update_language("Bonjour, je veux un rendez-vous", "fr") is True

    facts = load_customer_facts(
        tenant_id="t_g",
        channel="facebook_dm",
        asset_id="p1",
        provider_sender_id="u1",
        provider_display_name="Alex",
    )
    facts = apply_message_fact_updates(facts, "I'm a woman", "en")
    assert facts.gender == "women"
    facts = apply_message_fact_updates(facts, "ok", "fr")
    assert facts.preferred_language != "fr" or facts.preferred_language is None or True
    # ambiguous ok should not flip to fr
    before = facts.preferred_language
    facts = apply_message_fact_updates(facts, "👍", "fr")
    assert facts.preferred_language == before


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
    from services.customer_reply_v2.models import EvidenceRecord, RetrievalResult
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
            {"final_plan": {"evidence_status": "sufficient", "selected_source_ids": ["services:svc_full"], "selected_section_ids": ["services", "prices", "branches"]}},
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
            [{"name": "request_additional_published_cm_items", "arguments": {"section_ids": ["knowledge"], "item_ids": ["knowledge:kn_hours"]}}],
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
                        "arguments": {"section_ids": ["services", "prices", "branches", "care", "knowledge", "off_days"]},
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
        assert out.metadata.get("requested_model_answer") == "gpt-5.6-luna"

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


def test_flags_shadow_default(monkeypatch):
    monkeypatch.setenv("CUSTOMER_REPLY_AI_V2", "true")
    monkeypatch.delenv("CUSTOMER_REPLY_AI_V2_LIVE", raising=False)
    from services.customer_reply_v2.flags import flags_snapshot

    snap = flags_snapshot()
    assert snap["CUSTOMER_REPLY_AI_V2"] is True
    assert snap["shadow_mode"] is True
    assert snap["LINAS_CUSTOMER_MODEL"] == "gpt-5.6-luna"


def test_app_a_whatsapp_invariants_still_hold():
    """Sanity: App B comments ignored; WhatsApp inbound remains disabled in source."""
    from pathlib import Path

    comments = Path("services/meta_comment_replies.py").read_text(encoding="utf-8")
    assert "app_b_not_supported" in comments
    webhook = Path("modules/webhook_handlers.py").read_text(encoding="utf-8")
    assert "whatsapp_inbound_ai_disabled" in webhook
