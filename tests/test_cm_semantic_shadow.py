"""CM Phase 5: hash embeddings + semantic index retrieval, interpreter, shadow no-side-effects."""

from __future__ import annotations

import pytest

from services.ai_setup.embeddings import HASH_EMBEDDING_DIMENSIONS, cosine_similarity, embed_texts, embedding_pin
from services.ai_setup.paths import indexes_dir
from tests.cm_semantic_index import build_index, load_index, search

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
