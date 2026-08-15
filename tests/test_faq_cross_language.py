"""Cross-language Smart Q&A matching and answer localization."""

from __future__ import annotations

import pytest

pytest_plugins = ("tests.customer_reply_ai_v2_fixtures",)

from services.customer_reply_v2.faq_fast_path import try_faq_fast_path
from services.faq_answer_localize import localize_faq_answer


@pytest.mark.asyncio
async def test_localize_faq_answer_same_language_is_noop() -> None:
    answer = await localize_faq_answer(
        answer="We open at 10am.",
        source_language="en",
        target_language="en",
    )
    assert answer == "We open at 10am."


@pytest.mark.asyncio
async def test_localize_faq_answer_translates_to_visitor_language(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_translate(answer: str, *, source_language: str | None = None, target_language: str | None = None) -> str:
        assert source_language == "en"
        assert target_language == "ur"
        return "ہم صبح دس بجے کھلتے ہیں۔"

    monkeypatch.setattr(
        "services.language_detection_service.language_detection_service.translate_answer_text",
        _fake_translate,
    )
    localized = await localize_faq_answer(
        answer="We open at 10am.",
        source_language="en",
        target_language="ur",
    )
    assert localized == "ہم صبح دس بجے کھلتے ہیں۔"


@pytest.mark.asyncio
async def test_faq_fast_path_localizes_cross_language_tier_hit(v2_env, monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.cm_test_helpers import publish_test_content
    from tests.customer_reply_ai_v2_helpers import _rich_sections

    await publish_test_content("t_xlang", _rich_sections())

    async def _fake_tier(message, lang):
        return {
            "tier": "direct",
            "match_score": 0.95,
            "matched_language": "en",
            "qa_pair": {"answer": "We open 10am to 6pm.", "language": "en"},
        }

    async def _fake_translate(answer: str, *, source_language: str | None = None, target_language: str | None = None) -> str:
        return "ہم صبح دس بجے سے شام چھ بجے تک کھلے رہتے ہیں۔"

    monkeypatch.setattr("services.local_qa_service.local_qa_service.find_match_with_tier", _fake_tier)
    monkeypatch.setattr(
        "services.language_detection_service.language_detection_service.translate_answer_text",
        _fake_translate,
    )

    hit = await try_faq_fast_path(
        tenant_id="t_xlang",
        message="آپ کے اوقات کار کیا ہیں؟",
        detected_language="ur",
        response_language="ur",
    )
    assert hit.hit is True
    assert hit.answer == "ہم صبح دس بجے سے شام چھ بجے تک کھلے رہتے ہیں۔"
    assert hit.metadata is not None
    assert hit.metadata.get("matched_language") == "en"
    assert hit.metadata.get("response_language") == "ur"


@pytest.mark.asyncio
async def test_faq_fast_path_semantic_cross_language_fallback(v2_env, monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.cm_test_helpers import publish_test_content
    from tests.customer_reply_ai_v2_helpers import _rich_sections

    await publish_test_content("t_xlang_sem", _rich_sections())

    async def _no_tier(*_args, **_kwargs):
        return None

    monkeypatch.setattr("services.local_qa_service.local_qa_service.find_match_with_tier", _no_tier)

    calls: list[str | None] = []

    async def _fake_semantic(*, tenant_id, index_id, query, kind, language, top_k):
        calls.append(language)
        if language is None:
            return [
                {
                    "score": 0.93,
                    "source_id": "faq:1",
                    "metadata": {
                        "answer": "Laser sessions start at twenty dollars.",
                        "language": "en",
                    },
                }
            ]
        return []

    async def _fake_translate(answer: str, *, source_language: str | None = None, target_language: str | None = None) -> str:
        return "لیزر سیشن بیس ڈالر سے شروع ہوتے ہیں۔"

    monkeypatch.setattr("services.cm.semantic_index.search", _fake_semantic)
    monkeypatch.setattr(
        "services.language_detection_service.language_detection_service.translate_answer_text",
        _fake_translate,
    )

    hit = await try_faq_fast_path(
        tenant_id="t_xlang_sem",
        message="لیزر کی قیمت کیا ہے؟",
        detected_language="ur",
        response_language="ur",
    )
    assert hit.hit is True
    assert hit.reason == "faq_semantic"
    assert calls == ["ur", None]
    assert hit.answer == "لیزر سیشن بیس ڈالر سے شروع ہوتے ہیں۔"
