"""CM handler integration: Customer Reply AI V2 is the sole generative engine."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from handlers.text_handlers_respond import _handle_published_cm_runtime
from services.customer_reply_v2.models import CustomerReplyOutcome
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
    assert metadata.get("classic_fallback") is False


@pytest.mark.asyncio
async def test_restricted_topic_short_circuits_without_classic_generate() -> None:
    from services.cm.schemas import initial_restricted_policy

    tenant_id = "cm_handler_test_restricted"
    await publish_test_content(
        tenant_id,
        {"restricted": initial_restricted_policy(active=True).model_dump(mode="json")},
    )

    with patch("services.cm.answer_generation.generate_answer_with_usage", new_callable=AsyncMock) as mock_gen:
        reply, metadata = await _handle_published_cm_runtime(
            tenant_id=tenant_id,
            message="I want tattoo removal please",
            detected_language="en",
            response_language="en",
        )
    mock_gen.assert_not_awaited()
    assert metadata["reason"] == "restricted"
    assert reply
    assert metadata.get("classic_fallback") is False


@pytest.mark.asyncio
async def test_faq_hit_short_circuits_without_classic_generate() -> None:
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
        with patch("services.cm.answer_generation.generate_answer_with_usage", new_callable=AsyncMock) as mock_gen:
            reply, metadata = await _handle_published_cm_runtime(
                tenant_id=tenant_id,
                message="what are your opening hours",
                detected_language="en",
                response_language="en",
            )
        mock_gen.assert_not_awaited()
        assert metadata["reason"] in ("faq_exact", "faq_direct")
        assert "9am" in reply or "6pm" in reply
        assert metadata.get("classic_fallback") is False
    finally:
        local_qa_service.qa_pairs[:] = original_pairs


@pytest.mark.asyncio
async def test_v2_generated_reply_never_calls_classic_generate() -> None:
    tenant_id = "cm_handler_test_packet"
    await publish_test_content(tenant_id)

    outcome = CustomerReplyOutcome(
        stop=True,
        reply="A friendly, on-language answer with no invented facts.",
        reason="v2_generated",
        evidence_status="sufficient",
        metadata={
            "validated": True,
            "classic_fallback": False,
            "prompt_tokens": 100,
            "completion_tokens": 40,
            "tokens": 140,
            "model": "gpt-5.6-terra",
            "requested_model_retrieval": "gpt-5.6-luna",
            "requested_model_answer": "gpt-5.6-terra",
            "reasoning_effort_answer": "medium",
        },
    )

    with (
        patch(
            "services.customer_reply_v2.orchestrator.run_customer_reply_v2_dm",
            new=AsyncMock(return_value=outcome),
        ),
        patch("services.cm.answer_generation.generate_answer_with_usage", new_callable=AsyncMock) as mock_gen,
    ):
        reply, metadata = await _handle_published_cm_runtime(
            tenant_id=tenant_id,
            message="Tell me something about your clinic",
            detected_language="en",
            response_language="en",
        )
    mock_gen.assert_not_awaited()
    assert metadata["reason"] == "v2_generated"
    assert metadata["customer_reply_ai_v2"] is True
    assert metadata["classic_fallback"] is False
    assert reply == "A friendly, on-language answer with no invented facts."
    assert metadata["requested_model_retrieval"] == "gpt-5.6-luna"
    assert metadata["requested_model_answer"] == "gpt-5.6-terra"


@pytest.mark.asyncio
async def test_v2_exception_fails_closed_without_classic() -> None:
    tenant_id = "cm_handler_test_packet_invalid"
    await publish_test_content(tenant_id)

    with (
        patch(
            "services.customer_reply_v2.orchestrator.run_customer_reply_v2_dm",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ),
        patch("services.cm.answer_generation.generate_answer_with_usage", new_callable=AsyncMock) as mock_gen,
    ):
        reply, metadata = await _handle_published_cm_runtime(
            tenant_id=tenant_id,
            message="How much does it cost?",
            detected_language="en",
            response_language="en",
        )
    mock_gen.assert_not_awaited()
    assert metadata["reason"] == "v2_failed_closed"
    assert metadata["classic_fallback"] is False
    assert reply
