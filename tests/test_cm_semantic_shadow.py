"""CM Phase 5: hash embeddings + semantic index retrieval, interpreter, shadow no-side-effects."""

from __future__ import annotations

import copy

import pytest

from services.cm.embeddings import HASH_EMBEDDING_DIMENSIONS, cosine_similarity, embed_texts, embedding_pin
from services.cm.paths import indexes_dir
from services.cm.query_interpreter import interpret_query, interpret_query_deterministic, interpreter_llm_enabled
from services.cm.schemas import RestrictedPolicy, ServicesSection, initial_restricted_policy
from services.cm.semantic_index import build_index, load_index, search
from services.cm.shadow_eval import run_shadow_eval
from services.local_qa_service import local_qa_service

pytestmark = pytest.mark.usefixtures("enable_faq_plan")


@pytest.fixture(autouse=True)
def _hash_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CM_EMBEDDING_PROVIDER", "hash")


# --------------------------- embeddings ---------------------------


def test_embedding_pin_reports_hash_provider() -> None:
    pin = embedding_pin()
    assert pin.provider == "hash"
    assert pin.dimensions == HASH_EMBEDDING_DIMENSIONS


@pytest.mark.asyncio
async def test_hash_embedding_is_deterministic() -> None:
    vec1 = await embed_texts(["What is the laser price?"])
    vec2 = await embed_texts(["What is the laser price?"])
    assert vec1 == vec2
    assert len(vec1[0]) == HASH_EMBEDDING_DIMENSIONS


@pytest.mark.asyncio
async def test_hash_embedding_distinguishes_different_text() -> None:
    vec_a, vec_b = await embed_texts(["laser hair removal price", "branch opening hours today"])
    assert vec_a != vec_b
    assert cosine_similarity(vec_a, vec_a) == pytest.approx(1.0, abs=1e-6)


# --------------------------- semantic index ---------------------------


@pytest.mark.asyncio
async def test_build_index_and_search_retrieves_relevant_faq() -> None:
    tenant_id = "cm_semantic_test_faq"
    sections = {
        "faq": {
            "items": [
                {
                    "qa_group_id": "qa_price",
                    "variants": [
                        {"language": "en", "question": "What is the laser hair removal price?", "answer": "20 USD"},
                        {"language": "ar", "question": "شو سعر إزالة الشعر بالليزر؟", "answer": "٢٠ دولار"},
                    ],
                    "tags": [],
                },
                {
                    "qa_group_id": "qa_hours",
                    "variants": [
                        {"language": "en", "question": "What are your opening hours?", "answer": "9am-9pm"},
                    ],
                    "tags": [],
                },
            ]
        },
        "knowledge": {"items": []},
        "care": {"items": []},
    }
    manifest = await build_index(tenant_id=tenant_id, content_version_id="v1", sections=sections, index_id="idx_test")
    assert manifest["entry_count"] == 3
    assert manifest["embedding"]["provider"] == "hash"

    loaded_manifest, rows = load_index(tenant_id, "idx_test")
    assert loaded_manifest["index_id"] == "idx_test"
    assert len(rows) == 3

    results = await search(
        tenant_id=tenant_id, index_id="idx_test", query="laser hair removal price", kind="faq", top_k=2
    )
    assert results
    assert results[0]["source_id"] == "faq:qa_price:en"
    assert "vector" not in results[0]


def test_index_is_tenant_scoped_on_disk() -> None:
    root_a = indexes_dir("tenant_a_semantic")
    root_b = indexes_dir("tenant_b_semantic")
    assert str(root_a) != str(root_b)
    assert "tenant_a_semantic" in str(root_a)
    assert "tenant_b_semantic" in str(root_b)


# --------------------------- query interpreter ---------------------------


def test_interpreter_llm_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CM_INTERPRETER_LLM", raising=False)
    assert interpreter_llm_enabled() is False


def test_deterministic_interpreter_extracts_booking_and_restricted() -> None:
    restricted = initial_restricted_policy(active=True)
    services = ServicesSection(items=[])
    result = interpret_query_deterministic(
        "I want to book an appointment for tattoo removal",
        services=services,
        restricted=restricted,
    )
    assert result.booking_requested is True
    assert result.restricted_topic_id == "tattoo_removal"
    assert result.used_llm is False


def test_deterministic_interpreter_no_false_positive_on_plain_question() -> None:
    result = interpret_query_deterministic("What is your address?", restricted=RestrictedPolicy())
    assert result.booking_requested is False
    assert result.human_requested is False
    assert result.restricted_topic_id is None


@pytest.mark.asyncio
async def test_interpret_query_is_skippable_via_use_llm_false() -> None:
    """MUST be skippable regardless of env — explicit use_llm=False never calls the LLM."""
    result = await interpret_query("book an appointment", use_llm=False)
    assert result.used_llm is False
    assert result.booking_requested is True


@pytest.mark.asyncio
async def test_interpret_query_defaults_to_deterministic_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CM_INTERPRETER_LLM", raising=False)
    result = await interpret_query("book an appointment")
    assert result.used_llm is False


# --------------------------- shadow eval ---------------------------


@pytest.mark.asyncio
async def test_shadow_eval_runs_only_on_provided_questions_and_reports_faq_hits() -> None:
    from services.cm.faq_integration import create_faq_pair

    tenant_id = "cm_shadow_test_basic"

    async def _fake_translate(question, answer, source_language=None, target_languages=None):
        targets = target_languages or []
        return {"success": True, "translations": {lang: {"question": question, "answer": answer} for lang in targets}}

    import services.cm.faq_integration as faq_integration_module

    original = faq_integration_module.language_detection_service.translate_training_pair
    faq_integration_module.language_detection_service.translate_training_pair = _fake_translate
    try:
        result = await create_faq_pair(
            question="unique shadow eval question",
            answer="شادو answer عربي",
            language="en",
            tenant_id=tenant_id,
        )
    finally:
        faq_integration_module.language_detection_service.translate_training_pair = original

    local_qa_service.qa_pairs = local_qa_service.load_from_jsonl()

    questions = [
        {"id": "hit-1", "question": "unique shadow eval question", "language": "en"},
        {"id": "miss-1", "question": "totally unrelated random miss question xyz", "language": "en"},
    ]
    report = await run_shadow_eval(tenant_id=tenant_id, questions=questions)
    report_dict = report.as_dict()

    assert report_dict["total_questions"] == 2
    assert report_dict["faq_hit_count"] == 1
    by_id = {r["id"]: r for r in report_dict["results"]}
    assert by_id["hit-1"]["faq_hit"] is True
    assert by_id["hit-1"]["interpreter_ran"] is False  # FAQ hit must skip interpreter
    assert by_id["miss-1"]["faq_hit"] is False
    assert by_id["miss-1"]["interpreter_ran"] is True
    assert result["qa_group_id"]


@pytest.mark.asyncio
async def test_shadow_eval_has_no_side_effects_on_qa_store_or_index() -> None:
    tenant_id = "cm_shadow_test_no_side_effects"
    before_qa_pairs = copy.deepcopy(local_qa_service.qa_pairs)
    index_root = indexes_dir(tenant_id)
    existed_before = index_root.exists()

    questions = [{"id": "q1", "question": "random shadow-only probe text", "language": "en"}]
    report = await run_shadow_eval(tenant_id=tenant_id, questions=questions)

    assert local_qa_service.qa_pairs == before_qa_pairs
    assert index_root.exists() == existed_before
    assert report.total_questions == 1
    assert report.results[0]["faq_hit"] is False
