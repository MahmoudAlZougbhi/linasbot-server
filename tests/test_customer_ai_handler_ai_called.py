"""Handler must not mask Brain fail-closed as validation-failed success."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from handlers.text_handlers_respond import _handle_published_cm_runtime
from services.customer_reply_v2.models import CustomerReplyOutcome
from tests.cm_test_helpers import install_mocked_openai_embeddings, publish_test_content


@pytest.fixture(autouse=True)
def _openai_published_embeddings(monkeypatch: pytest.MonkeyPatch) -> None:
    install_mocked_openai_embeddings(monkeypatch, published_mode=True)


@pytest.fixture(autouse=True)
def _cm_handler_credit_entitlement(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "services.credit_ai_gate.ai_generation_blocked",
        lambda *_a, **_k: False,
    )


@pytest.mark.asyncio
async def test_empty_brain_stop_is_brain_no_reply_not_validation_failed() -> None:
    tenant_id = "cm_handler_ai_called_empty"
    await publish_test_content(tenant_id)
    outcome = CustomerReplyOutcome(
        stop=True,
        reply=None,
        reason="index_not_ready",
        evidence_status="policy_stop",
        metadata={"ai_called": False, "cost_status": "none"},
    )
    with patch(
        "services.customer_reply_v2.orchestrator.run_customer_reply_v2_dm",
        new=AsyncMock(return_value=outcome),
    ):
        reply, metadata = await _handle_published_cm_runtime(
            tenant_id=tenant_id,
            message="price?",
            detected_language="en",
            response_language="en",
        )
    assert reply == ""
    assert metadata["reason"] == "index_not_ready"
    assert metadata.get("ai_called") is False
    assert metadata["pipeline_decisions"][0]["decision"] == "brain_no_reply"
    assert metadata["pipeline_decisions"][0]["ai_called"] is False


@pytest.mark.asyncio
async def test_generated_reply_marks_ai_generated() -> None:
    tenant_id = "cm_handler_ai_called_ok"
    await publish_test_content(tenant_id)
    outcome = CustomerReplyOutcome(
        stop=False,
        reply="Laser starts at 99 USD.",
        reason="v2_generated",
        evidence_status="sufficient",
        metadata={"ai_called": True, "cost_status": "tracked"},
    )
    with patch(
        "services.customer_reply_v2.orchestrator.run_customer_reply_v2_dm",
        new=AsyncMock(return_value=outcome),
    ):
        reply, metadata = await _handle_published_cm_runtime(
            tenant_id=tenant_id,
            message="price?",
            detected_language="en",
            response_language="en",
        )
    assert reply == "Laser starts at 99 USD."
    assert metadata.get("ai_called") is True
    assert metadata["pipeline_decisions"][0]["decision"] == "ai_generated"
    assert metadata["pipeline_decisions"][0]["ai_called"] is True


@pytest.mark.asyncio
async def test_reply_without_ai_called_metadata_stays_false() -> None:
    tenant_id = "cm_handler_ai_called_missing"
    await publish_test_content(tenant_id)
    outcome = CustomerReplyOutcome(
        stop=False,
        reply="Static FAQ answer",
        reason="ok",
        evidence_status="ok",
        metadata={"ai_called": False},
    )
    with patch(
        "services.customer_reply_v2.orchestrator.run_customer_reply_v2_dm",
        new=AsyncMock(return_value=outcome),
    ):
        reply, metadata = await _handle_published_cm_runtime(
            tenant_id=tenant_id,
            message="hours?",
            detected_language="en",
            response_language="en",
        )
    assert reply == "Static FAQ answer"
    assert metadata.get("ai_called") is False
    assert metadata["pipeline_decisions"][0]["decision"] == "brain_no_reply"
