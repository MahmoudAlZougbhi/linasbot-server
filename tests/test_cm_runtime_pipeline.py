"""CM Phase 6 runtime pipeline: exact order, FAQ-hit skip, restricted+booking, honest failure."""

from __future__ import annotations

import re

import pytest

from services.cm.embeddings import embedding_pin
from services.cm.runtime_pipeline import finalize_response, prepare_response
from services.cm.schemas import (
    HandoffContact,
    HandoffMatrixRow,
    HandoffPolicy,
    PublishedPointer,
    default_section_payload,
)
from services.cm.version_store import write_published_pointer, write_version_content
from services.local_qa_service import local_qa_service

_PHONE_RE = re.compile(r"\+\d{8,15}")


def _base_sections() -> dict[str, dict]:
    from services.cm.constants import CM_SECTIONS

    return {section: default_section_payload(section) for section in CM_SECTIONS}


async def _publish_fixture(tenant_id: str, overrides: dict[str, dict] | None = None) -> tuple[str, str | None]:
    sections = _base_sections()
    if overrides:
        sections.update(overrides)

    version_id = f"v_{tenant_id}"
    checksums = write_version_content(tenant_id, version_id, sections)
    pin = embedding_pin()
    pointer = PublishedPointer(
        content_version_id=version_id,
        index_version_id=None,
        checksums=checksums,
        embedding_provider=pin.provider,
        embedding_model=pin.model,
        embedding_version=pin.version,
        embedding_dimensions=pin.dimensions,
    )
    write_published_pointer(tenant_id, pointer)
    return version_id, None


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
    await _publish_fixture(tenant_id, {"handoff": _handoff_with_default_contact()})

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
    await _publish_fixture(tenant_id, {"handoff": _handoff_with_default_contact()})

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
    await _publish_fixture(tenant_id)  # default (empty) handoff policy

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
    await _publish_fixture(tenant_id)

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
    await _publish_fixture(tenant_id)

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
async def test_finalize_response_passthrough_when_valid() -> None:
    tenant_id = "cm_runtime_test_finalize_ok"
    await _publish_fixture(tenant_id)
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
    await _publish_fixture(tenant_id)
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
