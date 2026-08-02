"""CM FAQ bridge: 4-language auto-translate + Franco->Arabic answer contract (plan §8)."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from services.cm.constants import FAQ_EXACT_THRESHOLD
from services.cm.faq_integration import (
    FaqIntegrationError,
    _answer_in_arabic_script,
    create_faq_pair,
    list_cm_faq,
)
from services.local_qa_service import local_qa_service

FAKE_TRANSLATIONS: dict[str, dict[str, str]] = {
    "ar": {"question": "شو سعر الليزر؟", "answer": "السعر عشرين دولار."},
    "en": {"question": "What is the laser price?", "answer": "The price is twenty dollars."},
    "fr": {"question": "Quel est le prix du laser ?", "answer": "Le prix est de vingt dollars."},
    "franco": {"question": "shu se3r el laser?", "answer": "السعر عشرين دولار."},
}


async def _fake_translate_training_pair(
    question: str,
    answer: str,
    source_language: str | None = None,
    target_languages: list[str] | None = None,
) -> dict[str, Any]:
    targets = target_languages or []
    translations = {lang: dict(FAKE_TRANSLATIONS[lang]) for lang in targets if lang in FAKE_TRANSLATIONS}
    # Mirrors the real translate_training_pair: preserve source text exactly for the source language.
    if source_language and source_language in translations:
        translations[source_language] = {"question": question.strip(), "answer": answer.strip()}
    return {"success": True, "translations": translations}


@pytest.fixture(autouse=True)
def _mock_translation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "services.cm.faq_integration.language_detection_service.translate_training_pair",
        _fake_translate_training_pair,
    )


@pytest.mark.asyncio
async def test_faq_pair_has_four_linked_variants() -> None:
    result = await create_faq_pair(
        question="shu se3r el laser?",
        answer="ashreen dolar",
        language="franco",
        tags=["pricing"],
        tenant_id="cm_faq_test_variants",
    )
    assert result["success"] is True
    entries = result["created_entries"]
    languages = {entry["language"] for entry in entries}
    assert languages == {"ar", "en", "fr", "franco"}
    qa_group_ids = {entry["qa_group_id"] for entry in entries}
    assert qa_group_ids == {result["qa_group_id"]}
    assert result["record"]["tags"] == ["pricing"]
    assert len(result["record"]["variants"]) == 4


@pytest.mark.asyncio
async def test_franco_source_answer_is_arabic_script() -> None:
    result = await create_faq_pair(
        question="shu se3r el laser?",
        answer="ashreen dolar",
        language="franco",
        tenant_id="cm_faq_test_franco",
    )
    entries_by_lang = {entry["language"]: entry for entry in result["created_entries"]}

    # Franco question stays Latin/franco; its stored answer must be Arabic script.
    assert not _answer_in_arabic_script(entries_by_lang["franco"]["question"])
    assert _answer_in_arabic_script(entries_by_lang["franco"]["answer"])

    # AR row: both question and answer must be Arabic script (never Franco leaking into AR).
    assert _answer_in_arabic_script(entries_by_lang["ar"]["question"])
    assert _answer_in_arabic_script(entries_by_lang["ar"]["answer"])

    # EN/FR rows keep their own language answers (not forced to Arabic).
    assert not _answer_in_arabic_script(entries_by_lang["en"]["answer"])
    assert not _answer_in_arabic_script(entries_by_lang["fr"]["answer"])


@pytest.mark.asyncio
async def test_faq_pair_mirrors_group_metadata_into_cm_draft() -> None:
    tenant_id = f"cm_faq_test_mirror_{uuid.uuid4().hex[:8]}"
    result = await create_faq_pair(
        question="what is the laser price?",
        answer="twenty dollars",
        language="en",
        tags=["pricing", "laser"],
        tenant_id=tenant_id,
    )
    items = list_cm_faq(tenant_id=tenant_id)
    assert len(items) == 1
    assert items[0]["qa_group_id"] == result["qa_group_id"]
    assert items[0]["tags"] == ["pricing", "laser"]
    assert len(items[0]["variants"]) == 4


@pytest.mark.asyncio
async def test_faq_pair_appends_without_clobbering_existing_groups() -> None:
    tenant_id = f"cm_faq_test_multi_{uuid.uuid4().hex[:8]}"
    await create_faq_pair(question="q1", answer="a1", language="en", tenant_id=tenant_id)
    await create_faq_pair(question="q2", answer="a2", language="en", tenant_id=tenant_id)
    items = list_cm_faq(tenant_id=tenant_id)
    assert len(items) == 2
    assert len({item["qa_group_id"] for item in items}) == 2


@pytest.mark.asyncio
async def test_faq_pair_written_into_local_qa_jsonl_store() -> None:
    result = await create_faq_pair(
        question="unique jsonl question",
        answer="unique jsonl answer",
        language="en",
        tenant_id="cm_faq_test_jsonl",
    )
    qa_group_id = result["qa_group_id"]
    matching = [qa for qa in local_qa_service.qa_pairs if qa.get("qa_group_id") == qa_group_id]
    assert len(matching) == 4


@pytest.mark.asyncio
async def test_create_faq_pair_requires_question_and_answer() -> None:
    with pytest.raises(FaqIntegrationError):
        await create_faq_pair(question="", answer="", tenant_id="cm_faq_test_empty")


def test_exact_match_threshold_contract_is_090() -> None:
    """T4/T21 precondition: exact FAQ match must win before semantic; threshold is 0.90."""
    assert FAQ_EXACT_THRESHOLD == 0.90
    assert local_qa_service.match_threshold == FAQ_EXACT_THRESHOLD


@pytest.mark.asyncio
async def test_exact_match_wins_over_lower_score_before_semantic() -> None:
    tenant_id = "cm_faq_test_exact"
    question = "exact match unique probe question"
    await create_faq_pair(question=question, answer="exact answer", language="en", tenant_id=tenant_id)
    local_qa_service.qa_pairs = local_qa_service.load_from_jsonl()

    match = await local_qa_service.find_match_with_tier(question, "en")
    assert match is not None
    assert match["tier"] == "exact"
    assert match["match_score"] >= FAQ_EXACT_THRESHOLD
