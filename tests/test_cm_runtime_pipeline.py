"""CM Phase 6 runtime pipeline: exact order, FAQ-hit skip, restricted+booking, honest failure."""

from __future__ import annotations

import re

import pytest

from services.cm.runtime_pipeline import finalize_response, prepare_response
from services.cm.schemas import HandoffContact, HandoffMatrixRow, HandoffPolicy
from services.local_qa_service import local_qa_service
from tests.cm_test_helpers import install_mocked_openai_embeddings, publish_test_content

_PHONE_RE = re.compile(r"\+\d{8,15}")


@pytest.fixture(autouse=True)
def _openai_published_embeddings(monkeypatch: pytest.MonkeyPatch) -> None:
    install_mocked_openai_embeddings(monkeypatch, published_mode=True)


def _handoff_with_default_contact() -> dict:
    contact = HandoffContact(id="main", phone_e164="+96170000000", label="Main WhatsApp", gender="any")
    row = HandoffMatrixRow(id="row_main", contact_id="main", enabled=True, gender="any")
    return HandoffPolicy(contacts=[contact], matrix=[row]).model_dump(mode="json")


@pytest.mark.asyncio
async def test_no_published_version_is_honest_failure() -> None:
    outcome = await prepare_response(
        tenant_id="cm_runtime_test_missing",
        message="hello",
        detected_language="en",
        response_language="en",
    )
    assert outcome.stop is True
    assert outcome.reason == "no_published_version"
    assert outcome.reply is None
    assert outcome.error


@pytest.mark.asyncio
async def test_restricted_topic_refused_and_never_offers_handoff_number() -> None:
    """T7/T23: restricted + booking intent together must NEVER return a WhatsApp number."""
    tenant_id = "cm_runtime_test_restricted_booking"
    await publish_test_content(tenant_id, {"handoff": _handoff_with_default_contact()})

    outcome = await prepare_response(
        tenant_id=tenant_id,
        message="I want to book an appointment for tattoo removal",
        detected_language="en",
        response_language="en",
    )
    assert outcome.stop is True
    assert outcome.reason == "restricted"
    assert outcome.metadata["restricted_topic_id"] == "tattoo_removal"
    assert not _PHONE_RE.search(outcome.reply or "")


@pytest.mark.asyncio
async def test_booking_intent_without_restricted_resolves_handoff() -> None:
    tenant_id = "cm_runtime_test_handoff"
    await publish_test_content(tenant_id, {"handoff": _handoff_with_default_contact()})

    outcome = await prepare_response(
        tenant_id=tenant_id,
        message="I would like to book an appointment please",
        detected_language="en",
        response_language="en",
    )
    assert outcome.stop is True
    assert outcome.reason == "handoff"
    assert "+96170000000" in (outcome.reply or "")


@pytest.mark.asyncio
async def test_booking_intent_without_configured_contact_falls_through() -> None:
    """No invented WA number: with no handoff rows, booking intent must NOT stop the pipeline."""
    tenant_id = "cm_runtime_test_handoff_missing"
    await publish_test_content(tenant_id)  # default (empty) handoff policy

    outcome = await prepare_response(
        tenant_id=tenant_id,
        message="I would like to book an appointment please, totally unique probe text",
        detected_language="en",
        response_language="en",
    )
    assert outcome.reason != "handoff"
    assert not _PHONE_RE.search(outcome.reply or "")


@pytest.mark.asyncio
async def test_faq_hit_skips_interpreter_and_generative_call(monkeypatch: pytest.MonkeyPatch) -> None:
    """T21: FAQ hit must not call the Query Interpreter."""
    tenant_id = "cm_runtime_test_faq_hit"
    await publish_test_content(tenant_id)

    unique_question = "runtime pipeline unique faq hit probe question"
    local_qa_service.qa_pairs.append(
        {
            "question": unique_question,
            "answer": "runtime pipeline unique faq hit probe answer",
            "language": "en",
            "category": "test",
            "qa_group_id": "qa_runtime_pipeline_test",
        }
    )

    interpreter_calls = {"count": 0}

    async def _tracking_interpret_query(*args, **kwargs):
        interpreter_calls["count"] += 1
        raise AssertionError("Query Interpreter must not run on a FAQ hit")

    monkeypatch.setattr("services.cm.runtime_pipeline.interpret_query", _tracking_interpret_query)

    outcome = await prepare_response(
        tenant_id=tenant_id,
        message=unique_question,
        detected_language="en",
        response_language="en",
    )

    assert outcome.stop is True
    assert outcome.reason in ("faq_exact", "faq_direct")
    assert outcome.reply == "runtime pipeline unique faq hit probe answer"
    assert interpreter_calls["count"] == 0


@pytest.mark.asyncio
async def test_faq_miss_runs_interpreter_and_builds_packet() -> None:
    """T31: FAQ miss → Interpreter → structured+chunks → packet ready for the caller's large AI."""
    tenant_id = "cm_runtime_test_faq_miss"
    await publish_test_content(tenant_id)

    outcome = await prepare_response(
        tenant_id=tenant_id,
        message="totally unrelated probe text that matches nothing at all xyz123",
        detected_language="en",
        response_language="en",
    )
    assert outcome.stop is False
    assert outcome.reason == "packet_ready"
    assert outcome.packet is not None
    assert outcome.interpreted is not None
    assert outcome.packet.tenant_id == tenant_id
    assert outcome.packet.response_language == "en"


@pytest.mark.asyncio
async def test_hash_published_pointer_is_honest_failure_not_legacy_fallback() -> None:
    """Published mode must reject hash-labeled pointers instead of reading legacy content."""
    from services.cm.schemas import PublishedPointer, default_section_payload
    from services.cm.version_store import write_published_pointer, write_version_content

    tenant_id = "cm_runtime_test_hash_pointer"
    from services.cm.constants import CM_SECTIONS

    sections = {section: default_section_payload(section) for section in CM_SECTIONS}
    checksums = write_version_content(tenant_id, "v_hash", sections)
    write_published_pointer(
        tenant_id,
        PublishedPointer(
            content_version_id="v_hash",
            index_version_id="idx_hash",
            checksums=checksums,
            embedding_provider="hash",
            embedding_model="deterministic-hash-v1",
            embedding_version="1",
            embedding_dimensions=64,
        ),
    )
    outcome = await prepare_response(
        tenant_id=tenant_id,
        message="hello",
        detected_language="en",
        response_language="en",
    )
    assert outcome.stop is True
    assert outcome.reason == "invalid_published_embedding"
    assert outcome.reply is None


@pytest.mark.asyncio
async def test_finalize_response_passthrough_when_valid() -> None:
    tenant_id = "cm_runtime_test_finalize_ok"
    await publish_test_content(tenant_id)
    outcome = await prepare_response(
        tenant_id=tenant_id,
        message="another unrelated probe for finalize ok test",
        detected_language="en",
        response_language="en",
    )
    assert outcome.packet is not None
    result = await finalize_response(candidate_text="Hello, happy to help!", packet=outcome.packet)
    assert result.ok is True
    assert result.text == "Hello, happy to help!"


@pytest.mark.asyncio
async def test_finalize_response_validation_failed_message_path() -> None:
    """Validator blocks a bad price claim with no regen hook → honest answer_validation_failed message."""
    tenant_id = "cm_runtime_test_finalize_failed"
    await publish_test_content(tenant_id)
    outcome = await prepare_response(
        tenant_id=tenant_id,
        message="another unrelated probe for finalize failed test",
        detected_language="en",
        response_language="en",
    )
    assert outcome.packet is not None
    result = await finalize_response(candidate_text="The price is $999 for that.", packet=outcome.packet)
    assert result.ok is False
    assert "UNSUPPORTED_PRICE_CLAIM" in result.failed_rules
    assert result.text  # non-empty honest clarify/contact message
    assert "999" not in result.text
