"""CM handler integration: Customer Reply AI V2 is the sole generative engine."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from services.brain.inbound.text_handlers_respond import _handle_published_cm_runtime
from services.brain.reply.models import CustomerReplyOutcome
from tests.cm_test_helpers import install_mocked_openai_embeddings, publish_test_content


@pytest.fixture(autouse=True)
def _reset_temp_error_debounce() -> None:
    from services.brain.temporary_error_debounce import reset_temporary_error_debounce_for_tests

    reset_temporary_error_debounce_for_tests()
    yield
    reset_temporary_error_debounce_for_tests()


@pytest.fixture(autouse=True)
def _openai_published_embeddings(monkeypatch: pytest.MonkeyPatch) -> None:
    install_mocked_openai_embeddings(monkeypatch, published_mode=True)


@pytest.fixture(autouse=True)
def _cm_handler_credit_entitlement(monkeypatch: pytest.MonkeyPatch) -> None:
    """These tests exercise CM routing, not credit policy."""
    monkeypatch.setattr(
        "services.billing.credit_ai_gate.ai_generation_blocked",
        lambda *_a, **_k: False,
    )


@pytest.mark.asyncio
async def test_no_published_version_does_not_send_or_raise() -> None:
    reply, metadata = await _handle_published_cm_runtime(
        tenant_id="cm_handler_test_missing",
        message="hello",
        detected_language="en",
        response_language="en",
    )
    assert reply == ""
    assert metadata["reason"] != "engine_removed" or metadata.get("customer_engine") == "brain"
    assert metadata["reason"] in {
        "unpublished",
        "insufficient_credits",
        "insufficient_messages",
        "failed_closed",
        "index_not_ready",
    }
    assert metadata.get("classic_fallback") is False
    assert metadata.get("ai_called") is False


@pytest.mark.asyncio
async def test_published_runtime_does_not_call_classic_generate() -> None:
    from services.ai_setup.schemas import initial_restricted_policy

    tenant_id = "cm_handler_test_restricted"
    await publish_test_content(
        tenant_id,
        {"restricted": initial_restricted_policy(active=True).model_dump(mode="json")},
    )

    with patch("services.ai_setup.answer_generation.generate_answer_with_usage", new_callable=AsyncMock) as mock_gen:
        reply, metadata = await _handle_published_cm_runtime(
            tenant_id=tenant_id,
            message="I want tattoo removal please",
            detected_language="en",
            response_language="en",
        )
    mock_gen.assert_not_awaited()
    assert metadata.get("classic_fallback") is False
    assert (
        metadata["reason"]
        in {
            "unpublished",
            "insufficient_credits",
            "insufficient_messages",
            "restricted",
            "failed_closed",
            "index_not_ready",
        }
        or metadata.get("customer_engine") == "brain"
    )
    # Restricted may return a deterministic policy reply; never call classic generate.
    if metadata["reason"] != "restricted":
        assert reply == ""


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
            "requested_model_retrieval": "voyage-4-large",
            "requested_model_answer": "gpt-5.6-terra",
            "reasoning_effort_answer": "medium",
        },
    )

    with (
        patch(
            "services.brain.reply.orchestrator.run_customer_reply_v2_dm",
            new=AsyncMock(return_value=outcome),
        ),
        patch("services.ai_setup.answer_generation.generate_answer_with_usage", new_callable=AsyncMock) as mock_gen,
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
    assert metadata["requested_model_retrieval"] == "voyage-4-large"
    assert metadata["requested_model_answer"] == "gpt-5.6-terra"


@pytest.mark.asyncio
async def test_published_runtime_passes_inbound_message_id() -> None:
    tenant_id = "cm_handler_test_mid"
    await publish_test_content(tenant_id)
    captured: dict = {}

    async def capture_dm(**kwargs):
        captured.update(kwargs)
        return CustomerReplyOutcome(stop=False, reply="ok", reason="v2_generated")

    with patch("services.brain.reply.orchestrator.run_customer_reply_v2_dm", new=capture_dm):
        await _handle_published_cm_runtime(
            tenant_id=tenant_id,
            message="book me",
            detected_language="en",
            response_language="en",
            conversation_id="ig-thread-1",
            message_id="mid-ig-22",
        )
    assert captured["conversation_id"] == "ig-thread-1"
    assert captured["message_id"] == "mid-ig-22"


@pytest.mark.asyncio
async def test_insufficient_credits_short_circuits_without_classic_generate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = "cm_handler_test_no_credits"
    await publish_test_content(tenant_id)
    monkeypatch.setattr(
        "services.billing.credit_ai_gate.ai_generation_blocked",
        lambda *_a, **_k: True,
    )

    with patch("services.ai_setup.answer_generation.generate_answer_with_usage", new_callable=AsyncMock) as mock_gen:
        reply, metadata = await _handle_published_cm_runtime(
            tenant_id=tenant_id,
            message="How much does it cost?",
            detected_language="en",
            response_language="en",
        )
    mock_gen.assert_not_awaited()
    assert metadata.get("classic_fallback") is False
    assert (
        metadata["reason"]
        in {
            "unpublished",
            "insufficient_credits",
            "insufficient_messages",
            "restricted",
            "failed_closed",
            "index_not_ready",
        }
        or metadata.get("customer_engine") == "brain"
    )
    # Restricted may return a deterministic policy reply; never call classic generate.
    if metadata["reason"] != "restricted":
        assert reply == ""


@pytest.mark.asyncio
async def test_v2_exception_fails_closed_without_classic() -> None:
    tenant_id = "cm_handler_test_packet_invalid"
    await publish_test_content(tenant_id)

    with (
        patch(
            "services.brain.reply.orchestrator.run_customer_reply_v2_dm",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ),
        patch("services.ai_setup.answer_generation.generate_answer_with_usage", new_callable=AsyncMock) as mock_gen,
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
    assert metadata["exception_class"] == "RuntimeError"
    assert str(metadata.get("blocker") or "").startswith("RuntimeError:")
    from services.ai_setup.constants import ANSWER_VALIDATION_FAILED_MESSAGE_KEY, BRAIN_TEMPORARY_ERROR_MESSAGE_KEY
    from services.owner_copilot.dynamic_messages_service import get_dynamic_message

    expected = get_dynamic_message(BRAIN_TEMPORARY_ERROR_MESSAGE_KEY, "en")
    assert reply == ""
    assert reply != expected
    assert reply != get_dynamic_message(ANSWER_VALIDATION_FAILED_MESSAGE_KEY, "en")
    assert metadata.get("customer_silence") is True


@pytest.mark.asyncio
async def test_v2_exception_on_greeting_uses_opener_not_validator_copy() -> None:
    tenant_id = "cm_handler_test_greeting_fail"
    await publish_test_content(tenant_id)

    with (
        patch(
            "services.brain.reply.orchestrator.run_customer_reply_v2_dm",
            new=AsyncMock(side_effect=RuntimeError("openai timeout")),
        ),
        patch("services.ai_setup.answer_generation.generate_answer_with_usage", new_callable=AsyncMock) as mock_gen,
    ):
        reply, metadata = await _handle_published_cm_runtime(
            tenant_id=tenant_id,
            message="Hi kifak",
            detected_language="ar",
            response_language="ar",
        )
    mock_gen.assert_not_awaited()
    assert metadata["reason"] == "v2_failed_closed"
    assert metadata["greeting_fail_soft"] is False
    assert metadata["customer_silence"] is True
    assert metadata["exception_class"] == "RuntimeError"
    from services.ai_setup.constants import ANSWER_VALIDATION_FAILED_MESSAGE_KEY, BRAIN_TEMPORARY_ERROR_MESSAGE_KEY
    from services.owner_copilot.dynamic_messages_service import get_dynamic_message

    assert "ما قدرت أتأكد" not in reply
    assert reply != get_dynamic_message(ANSWER_VALIDATION_FAILED_MESSAGE_KEY, "ar")
    assert reply != get_dynamic_message(BRAIN_TEMPORARY_ERROR_MESSAGE_KEY, "ar")
    assert reply == ""
