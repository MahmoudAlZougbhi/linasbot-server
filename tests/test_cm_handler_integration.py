"""CM Phase 6: minimal handler integration (`handlers.text_handlers_respond`).

Verifies the ``CM_RUNTIME_MODE=published`` hook: FAQ/restricted short-circuits skip the large-AI
call entirely, a FAQ-miss packet routes through ``generate_answer`` + validator, and a missing
published pointer produces an honest failure message (never a silent legacy fallback).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from handlers.text_handlers_respond import _handle_published_cm_runtime
from services.local_qa_service import local_qa_service
from tests.cm_test_helpers import install_mocked_openai_embeddings, publish_test_content


@pytest.fixture(autouse=True)
def _openai_published_embeddings(monkeypatch: pytest.MonkeyPatch) -> None:
    install_mocked_openai_embeddings(monkeypatch, published_mode=True)


@pytest.mark.asyncio
async def test_no_published_version_returns_honest_failure_not_exception() -> None:
    reply, metadata = await _handle_published_cm_runtime(
        tenant_id="cm_handler_test_missing",
        message="hello",
        detected_language="en",
        response_language="en",
    )
    assert reply
    assert metadata["reason"] == "no_published_version"


@pytest.mark.asyncio
async def test_restricted_topic_short_circuits_without_calling_generate_answer() -> None:
    from services.cm.schemas import initial_restricted_policy

    tenant_id = "cm_handler_test_restricted"
    await publish_test_content(
        tenant_id,
        {"restricted": initial_restricted_policy(active=True).model_dump(mode="json")},
    )

    with patch("services.cm.answer_generation.generate_answer", new_callable=AsyncMock) as mock_gen:
        reply, metadata = await _handle_published_cm_runtime(
            tenant_id=tenant_id,
            message="I want tattoo removal please",
            detected_language="en",
            response_language="en",
        )
    mock_gen.assert_not_awaited()
    assert metadata["reason"] == "restricted"
    assert reply


@pytest.mark.asyncio
async def test_faq_hit_short_circuits_without_calling_generate_answer() -> None:
    tenant_id = "cm_handler_test_faq"
    await publish_test_content(tenant_id)

    original_pairs = list(local_qa_service.qa_pairs)
    local_qa_service.qa_pairs.append(
        {
            "id": "handler_faq_1",
            "qa_group_id": "handler_faq_group",
            "question": "what are your opening hours",
            "answer": "We are open 9am to 6pm.",
            "language": "en",
            "category": "content_manager",
            "tags": [],
        }
    )
    try:
        with patch("services.cm.answer_generation.generate_answer", new_callable=AsyncMock) as mock_gen:
            reply, metadata = await _handle_published_cm_runtime(
                tenant_id=tenant_id,
                message="what are your opening hours",
                detected_language="en",
                response_language="en",
            )
        mock_gen.assert_not_awaited()
        assert metadata["reason"] in ("faq_exact", "faq_direct")
        assert "9am" in reply or "6pm" in reply
    finally:
        local_qa_service.qa_pairs[:] = original_pairs


@pytest.mark.asyncio
async def test_packet_ready_calls_generate_answer_and_validates() -> None:
    tenant_id = "cm_handler_test_packet"
    await publish_test_content(tenant_id)

    with patch(
        "services.cm.answer_generation.generate_answer",
        new=AsyncMock(return_value="A friendly, on-language answer with no invented facts."),
    ):
        reply, metadata = await _handle_published_cm_runtime(
            tenant_id=tenant_id,
            message="Tell me something about your clinic",
            detected_language="en",
            response_language="en",
        )
    assert metadata["reason"] == "packet_ready"
    assert metadata["validated"] is True
    assert reply == "A friendly, on-language answer with no invented facts."


@pytest.mark.asyncio
async def test_packet_ready_validation_failure_returns_dynamic_message_and_no_regen_success() -> None:
    tenant_id = "cm_handler_test_packet_invalid"
    await publish_test_content(tenant_id)

    bad_reply = "Our price is $999 for that."

    async def _always_bad(_message, _packet):
        return bad_reply

    def _fake_make_regenerate_fn(_message, _packet):
        return _always_bad

    with (
        patch("services.cm.answer_generation.generate_answer", new=_always_bad),
        patch("services.cm.answer_generation.make_regenerate_fn", new=_fake_make_regenerate_fn),
    ):
        reply, metadata = await _handle_published_cm_runtime(
            tenant_id=tenant_id,
            message="How much does it cost?",
            detected_language="en",
            response_language="en",
        )
    assert metadata["reason"] == "answer_validation_failed"
    assert metadata["validated"] is False
    assert "UNSUPPORTED_PRICE_CLAIM" in metadata["failed_rules"]
    assert reply != bad_reply
