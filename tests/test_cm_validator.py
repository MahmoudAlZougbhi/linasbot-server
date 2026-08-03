"""CM Phase 6: deterministic response validator + finalize regeneration contract."""

from __future__ import annotations

import pytest

from services.cm.response_validator import (
    LANGUAGE_MISMATCH,
    PRICE_MISMATCH,
    RESTRICTED_SERVICE_OFFERED,
    UNSUPPORTED_PRICE_CLAIM,
    WA_NUMBER_MISMATCH,
    validate_response,
)
from services.cm.runtime_pipeline import finalize_response
from services.cm.schemas import AnswerFact, AnswerPacket


def _packet(**overrides) -> AnswerPacket:
    defaults = dict(
        tenant_id="cm_validator_test",
        content_version_id="v1",
        index_version_id=None,
        detected_language="en",
        response_language="en",
        facts=[],
        chunks=[],
    )
    defaults.update(overrides)
    return AnswerPacket(**defaults)


def test_validator_passes_clean_response() -> None:
    packet = _packet(facts=[AnswerFact(kind="price", value="20 USD", source_id="price:1")])
    result = validate_response("The laser session costs $20.", packet)
    assert result.ok is True
    assert result.failed_rules == []


def test_validator_blocks_bad_price_mismatch() -> None:
    packet = _packet(facts=[AnswerFact(kind="price", value="20 USD", source_id="price:1")])
    result = validate_response("The laser session costs $50.", packet)
    assert result.ok is False
    assert PRICE_MISMATCH in result.failed_rules


def test_validator_blocks_unsupported_price_claim_with_no_price_facts() -> None:
    packet = _packet(facts=[])
    result = validate_response("That will be $999 today.", packet)
    assert result.ok is False
    assert UNSUPPORTED_PRICE_CLAIM in result.failed_rules


def test_validator_blocks_wa_number_mismatch() -> None:
    packet = _packet(facts=[AnswerFact(kind="handoff_phone", value="+96170000000", source_id="handoff:1")])
    result = validate_response("Contact us at +96199999999.", packet)
    assert result.ok is False
    assert WA_NUMBER_MISMATCH in result.failed_rules


def test_validator_allows_matching_wa_number() -> None:
    packet = _packet(facts=[AnswerFact(kind="handoff_phone", value="+96170000000", source_id="handoff:1")])
    result = validate_response("Contact us at +96170000000.", packet)
    assert result.ok is True


def test_validator_blocks_restricted_service_offered() -> None:
    packet = _packet(facts=[AnswerFact(kind="service_available", value="true", source_id="service:tattoo_removal")])
    result = validate_response("Yes we offer that service.", packet, restricted_topic_active_ids={"tattoo_removal"})
    assert result.ok is False
    assert RESTRICTED_SERVICE_OFFERED in result.failed_rules


def test_validator_language_mismatch_for_arabic_response_language() -> None:
    packet = _packet(response_language="ar")
    result = validate_response("This is a plain English sentence with no Arabic at all.", packet)
    assert result.ok is False
    assert LANGUAGE_MISMATCH in result.failed_rules


def test_validator_arabic_response_passes_for_arabic_language() -> None:
    packet = _packet(response_language="ar")
    result = validate_response("مرحباً، السعر عشرين دولار.", packet)
    assert result.ok is True


@pytest.mark.asyncio
async def test_finalize_response_regenerates_once_then_succeeds() -> None:
    packet = _packet(facts=[AnswerFact(kind="price", value="20 USD", source_id="price:1")])

    async def _regenerate(previous_text: str, failed_rules: list[str]) -> str:
        assert PRICE_MISMATCH in failed_rules
        return "The laser session costs $20."

    result = await finalize_response(
        candidate_text="The laser session costs $50.", packet=packet, regenerate_fn=_regenerate
    )
    assert result.ok is True
    assert result.regenerated is True
    assert result.text == "The laser session costs $20."


@pytest.mark.asyncio
async def test_finalize_response_regenerates_at_most_once_then_honest_failure() -> None:
    packet = _packet(facts=[AnswerFact(kind="price", value="20 USD", source_id="price:1")])
    call_count = {"n": 0}

    async def _still_bad_regenerate(previous_text: str, failed_rules: list[str]) -> str:
        call_count["n"] += 1
        return "Still $999, sorry."

    result = await finalize_response(
        candidate_text="The laser session costs $50.", packet=packet, regenerate_fn=_still_bad_regenerate
    )
    assert result.ok is False
    assert call_count["n"] == 1  # at most one constrained regeneration
    assert PRICE_MISMATCH in result.failed_rules
    assert result.text  # honest answer_validation_failed message, not the invalid text
    assert "999" not in result.text


@pytest.mark.asyncio
async def test_finalize_response_without_regenerate_fn_returns_honest_failure_immediately() -> None:
    packet = _packet(facts=[])
    result = await finalize_response(candidate_text="It costs $10.", packet=packet)
    assert result.ok is False
    assert result.regenerated is False
    assert UNSUPPORTED_PRICE_CLAIM in result.failed_rules


@pytest.mark.asyncio
async def test_finalize_response_failure_message_is_language_aware() -> None:
    packet_ar = _packet(response_language="ar", facts=[])
    result_ar = await finalize_response(candidate_text="It costs $10.", packet=packet_ar)
    assert result_ar.ok is False
    assert any("\u0600" <= ch <= "\u06ff" for ch in result_ar.text)
