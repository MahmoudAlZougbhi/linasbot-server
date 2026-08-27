"""Customer AI V10 Phase 2 — strict FAQ direct path."""

from __future__ import annotations

import pytest

from tests.cm_test_helpers import publish_test_content
from tests.customer_reply_ai_v2_helpers import _rich_sections

pytest_plugins = ("tests.customer_reply_ai_v2_fixtures",)


def _hours_tier(message: str, _lang: str):
    if "أوقات" in message or "دوام" in message:
        return {
            "tier": "exact",
            "match_score": 1.0,
            "matched_language": "ar",
            "qa_pair": {
                "id": "faq_hours",
                "qa_group_id": "faq_hours",
                "revision": "7",
                "question": "شو أوقات الدوام؟",
                "answer": "من الاثنين للسبت من 10 إلى 8.",
                "language": "ar",
            },
        }
    if "hours" in message.lower():
        return {
            "tier": "exact",
            "match_score": 1.0,
            "matched_language": "en",
            "qa_pair": {
                "id": "faq_hours",
                "qa_group_id": "faq_hours",
                "revision": "7",
                "question": "What are your hours?",
                "answer": "We open 10am to 6pm.",
                "language": "en",
            },
        }
    return None


async def _install_hours_faq(monkeypatch: pytest.MonkeyPatch):
    async def _fake_tier(message, lang):
        return _hours_tier(message, lang)

    monkeypatch.setattr("services.local_qa_service.local_qa_service.find_match_with_tier", _fake_tier)


def _assert_no_ai_charge(out) -> None:
    metering = (out.metadata or {}).get("metering") or {}
    assert metering.get("ai_invocation_count") == 0
    ops = [row["operation"] for row in metering.get("invocations") or []]
    assert "luna_retrieval" not in ops
    assert "tera_answer" not in ops
    assert "faq_direct_reply" in ops
    assert out.metadata.get("ai_called") is False


@pytest.mark.asyncio
async def test_exact_faq_dm_direct_no_luna_tera(v2_env, monkeypatch: pytest.MonkeyPatch):
    await publish_test_content("t_faq2", _rich_sections())
    await _install_hours_faq(monkeypatch)

    async def _boom(**_k):
        raise AssertionError("Luna/Tera must not run on FAQ direct")

    monkeypatch.setattr("services.customer_reply_v2.orchestrator_llm.run_retrieval_luna", _boom)
    monkeypatch.setattr("services.customer_reply_v2.orchestrator_llm.run_answer_luna", _boom)

    from services.customer_reply_v2.orchestrator import run_customer_reply_v2_dm

    out = await run_customer_reply_v2_dm(
        tenant_id="t_faq2",
        message="What are your hours?",
        detected_language="en",
        response_language="en",
        channel="instagram_dm",
        provider_sender_id="u1",
    )
    assert out.evidence_status == "faq_hit"
    assert out.reply == "We open 10am to 6pm."
    assert out.metadata["faq"]["faq_id"] == "faq_hours"
    assert out.metadata["faq"]["faq_revision"] == "7"
    assert out.metadata["trace"]["faq_direct_reply"] is True
    _assert_no_ai_charge(out)


@pytest.mark.asyncio
async def test_semantic_full_message_faq_direct(v2_env, monkeypatch: pytest.MonkeyPatch):
    await publish_test_content("t_faq_sem", _rich_sections())

    async def _no_tier(*_a, **_k):
        return None

    async def _semantic(*, tenant_id, index_id, query, kind, language, top_k):
        return [
            {
                "score": 0.94,
                "source_id": "faq_hours",
                "metadata": {
                    "question": "What are your opening hours?",
                    "answer": "We open 10am to 6pm.",
                    "language": "en",
                    "revision": "2",
                },
            }
        ]

    monkeypatch.setattr("services.local_qa_service.local_qa_service.find_match_with_tier", _no_tier)
    monkeypatch.setattr("services.cm.semantic_index.search", _semantic)
    from services.customer_reply_v2.faq_fast_path import try_faq_fast_path

    hit = await try_faq_fast_path(
        tenant_id="t_faq_sem",
        message="What are your opening hours?",
        detected_language="en",
        response_language="en",
        channel="instagram_dm",
    )
    assert hit.hit is True
    assert hit.reason == "faq_semantic"
    assert hit.metadata["faq_id"] == "faq_hours"
    assert hit.metadata["match_score"] == 0.94


@pytest.mark.asyncio
async def test_faq_miss_goes_to_luna(v2_env, monkeypatch: pytest.MonkeyPatch):
    await publish_test_content("t_faq_miss", _rich_sections())

    async def _no_tier(*_a, **_k):
        return None

    async def _no_sem(**_k):
        return []

    monkeypatch.setattr("services.local_qa_service.local_qa_service.find_match_with_tier", _no_tier)
    monkeypatch.setattr("services.cm.semantic_index.search", _no_sem)

    from services.customer_reply_v2.models import AnswerLunaResult, RetrievalResult
    from services.customer_reply_v2.orchestrator import run_customer_reply_v2_dm

    called = {"luna": False}

    async def _luna(**_k):
        called["luna"] = True
        return RetrievalResult(evidence=[], evidence_status="sufficient", rounds_used=1, selected_source_ids=[])

    async def _tera(**_k):
        return AnswerLunaResult(reply_text="ok", grounding_status="grounded")

    monkeypatch.setattr("services.customer_reply_v2.orchestrator_llm.run_retrieval_luna", _luna)
    monkeypatch.setattr("services.customer_reply_v2.orchestrator_llm.run_answer_luna", _tera)
    monkeypatch.setattr("services.customer_reply_v2.orchestrator_answer.run_answer_luna", _tera)

    out = await run_customer_reply_v2_dm(
        tenant_id="t_faq_miss",
        message="Do you sell spaceships?",
        detected_language="en",
        response_language="en",
        provider_sender_id="u_miss",
        fixture_answer={"reply_text": "ok", "grounding_status": "grounded"},
        scripted_retrieval=[{"final_plan": {"evidence_status": "sufficient", "selected_source_ids": []}}],
    )
    assert called["luna"] is True
    assert out.metadata.get("faq_direct_reply") is False


@pytest.mark.asyncio
async def test_faq_plus_extra_question_not_direct(v2_env, monkeypatch: pytest.MonkeyPatch):
    await publish_test_content("t_faq_mix", _rich_sections())
    await _install_hours_faq(monkeypatch)
    from services.customer_reply_v2.faq_eligibility import FaqTurnGuards
    from services.customer_reply_v2.faq_fast_path import try_faq_fast_path

    hit = await try_faq_fast_path(
        tenant_id="t_faq_mix",
        message="شو أوقات الدوام؟",
        detected_language="ar",
        response_language="ar",
        channel="instagram_dm",
    )
    assert hit.hit is True
    assert "10" in (hit.answer or "")

    mixed = await try_faq_fast_path(
        tenant_id="t_faq_mix",
        message="شو أوقات الدوام وبدي موعد الخميس؟",
        detected_language="ar",
        response_language="ar",
        guards=FaqTurnGuards(channel="instagram_dm"),
        channel="instagram_dm",
    )
    assert mixed.hit is False
    assert mixed.reason in {"mixed_intent", "partial_coverage", "greeting_plus_question"}
    assert mixed.evidence_candidates
    assert mixed.evidence_candidates[0]["faq_id"] == "faq_hours"


@pytest.mark.asyncio
async def test_faq_plus_appointment_not_direct(v2_env, monkeypatch: pytest.MonkeyPatch):
    await publish_test_content("t_faq_apt", _rich_sections())
    await _install_hours_faq(monkeypatch)
    from services.customer_reply_v2.faq_fast_path import try_faq_fast_path

    hit = await try_faq_fast_path(
        tenant_id="t_faq_apt",
        message="What are your hours? I want an appointment Thursday.",
        detected_language="en",
        response_language="en",
        channel="instagram_dm",
    )
    assert hit.hit is False
    assert hit.reason == "mixed_intent"


@pytest.mark.asyncio
async def test_open_draft_blocks_faq_direct(v2_env, monkeypatch: pytest.MonkeyPatch):
    await publish_test_content("t_faq_draft", _rich_sections())
    await _install_hours_faq(monkeypatch)
    monkeypatch.setattr(
        "services.customer_reply_v2.orchestrator_faq.has_open_collecting_draft",
        lambda **_k: True,
    )
    from services.customer_reply_v2.orchestrator_faq import evaluate_faq_turn

    faq = await evaluate_faq_turn(
        tenant_id="t_faq_draft",
        message="What are your hours?",
        detected_language="en",
        response_language="en",
        channel="instagram_dm",
        customer_id="u_draft",
    )
    assert faq.hit is False
    assert faq.reason == "open_draft"


@pytest.mark.asyncio
async def test_attachment_and_reply_to_block_faq(v2_env, monkeypatch: pytest.MonkeyPatch):
    await publish_test_content("t_faq_att", _rich_sections())
    await _install_hours_faq(monkeypatch)
    from services.customer_reply_v2.faq_eligibility import FaqTurnGuards
    from services.customer_reply_v2.faq_fast_path import try_faq_fast_path

    att = await try_faq_fast_path(
        tenant_id="t_faq_att",
        message="What are your hours?",
        detected_language="en",
        guards=FaqTurnGuards(has_attachment=True, channel="instagram_dm"),
        channel="instagram_dm",
    )
    assert att.hit is False
    assert att.reason == "attachment"
    reply = await try_faq_fast_path(
        tenant_id="t_faq_att",
        message="What are your hours?",
        detected_language="en",
        guards=FaqTurnGuards(has_reply_to=True, channel="instagram_dm"),
        channel="instagram_dm",
    )
    assert reply.reason == "reply_to"


@pytest.mark.asyncio
async def test_ai_guidance_comment_rule_blocks_faq(v2_env, monkeypatch: pytest.MonkeyPatch):
    await publish_test_content("t_faq_cmt", _rich_sections())
    await _install_hours_faq(monkeypatch)
    from services.customer_reply_v2.faq_eligibility import FaqTurnGuards
    from services.customer_reply_v2.faq_fast_path import try_faq_fast_path

    hit = await try_faq_fast_path(
        tenant_id="t_faq_cmt",
        message="What are your hours?",
        detected_language="en",
        guards=FaqTurnGuards(has_ai_guidance_comment_rule=True, channel="instagram_comment"),
        channel="instagram_comment",
    )
    assert hit.hit is False
    assert hit.reason == "ai_guidance_comment_rule"


@pytest.mark.asyncio
async def test_language_mismatch_does_not_translate(v2_env, monkeypatch: pytest.MonkeyPatch):
    await publish_test_content("t_faq_lang", _rich_sections())
    await _install_hours_faq(monkeypatch)
    translated = {"called": False}

    async def _translate(answer, **_k):
        translated["called"] = True
        return "translated"

    monkeypatch.setattr(
        "services.language_detection_service.language_detection_service.translate_answer_text",
        _translate,
    )
    from services.customer_reply_v2.faq_fast_path import try_faq_fast_path

    hit = await try_faq_fast_path(
        tenant_id="t_faq_lang",
        message="What are your hours?",
        detected_language="en",
        response_language="ur",
        channel="instagram_dm",
    )
    assert hit.hit is False
    assert hit.reason == "language_mismatch"
    assert translated["called"] is False
    assert hit.evidence_candidates


@pytest.mark.asyncio
async def test_published_language_variant_used_without_ai(v2_env, monkeypatch: pytest.MonkeyPatch):
    await publish_test_content("t_faq_var", _rich_sections())
    await _install_hours_faq(monkeypatch)
    from services.customer_reply_v2.faq_fast_path import try_faq_fast_path

    hit = await try_faq_fast_path(
        tenant_id="t_faq_var",
        message="What are your hours?",
        detected_language="en",
        response_language="ar",
        channel="instagram_dm",
    )
    assert hit.hit is True
    assert hit.answer == "منفتح من ١٠ ل ٦."
    assert hit.metadata.get("localized") is False


@pytest.mark.asyncio
async def test_greeting_plus_faq_goes_full_flow(v2_env, monkeypatch: pytest.MonkeyPatch):
    await publish_test_content("t_faq_hi", _rich_sections())
    await _install_hours_faq(monkeypatch)
    from services.customer_reply_v2.faq_fast_path import try_faq_fast_path

    hit = await try_faq_fast_path(
        tenant_id="t_faq_hi",
        message="Hi, What are your hours?",
        detected_language="en",
        response_language="en",
        channel="instagram_dm",
    )
    assert hit.hit is False
    assert hit.reason == "greeting_plus_question"


@pytest.mark.asyncio
async def test_legacy_flag_still_localizes(v2_env, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CUSTOMER_AI_V10_RUNTIME", "false")
    await publish_test_content("t_faq_legacy", _rich_sections())
    await _install_hours_faq(monkeypatch)

    async def _translate(answer, **_k):
        return "translated-legacy"

    monkeypatch.setattr(
        "services.language_detection_service.language_detection_service.translate_answer_text",
        _translate,
    )
    from services.customer_reply_v2.faq_fast_path import try_faq_fast_path

    hit = await try_faq_fast_path(
        tenant_id="t_faq_legacy",
        message="What are your hours?",
        detected_language="en",
        response_language="ur",
        channel="instagram_dm",
        strict=False,
    )
    assert hit.hit is True
    assert hit.answer == "translated-legacy"
