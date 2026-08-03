"""Prove published-mode semantic embeddings are real (openai) and hash is test-only."""

from __future__ import annotations

import pytest

from services.cm.embeddings import (
    OPENAI_EMBEDDING_MODEL_DEFAULT,
    HashEmbeddingForbiddenError,
    PublishedEmbeddingError,
    assert_embedding_provider_allowed,
    assert_published_embedding_pin,
    embed_texts,
    embedding_pin,
    embedding_provider_name,
)
from services.cm.semantic_index import build_index, search
from tests.cm_test_helpers import install_mocked_openai_embeddings


def test_default_provider_name_is_openai_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CM_EMBEDDING_PROVIDER", raising=False)
    assert embedding_provider_name() == "openai"
    pin = embedding_pin()
    assert pin.provider == "openai"
    assert pin.model == OPENAI_EMBEDDING_MODEL_DEFAULT


def test_hash_allowed_in_test_harness_when_legacy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("CM_EMBEDDING_PROVIDER", "hash")
    monkeypatch.setenv("CM_RUNTIME_MODE", "legacy")
    assert assert_embedding_provider_allowed() == "hash"


def test_hash_forbidden_outside_test_harness(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("CM_EMBEDDING_PROVIDER", "hash")
    monkeypatch.setenv("CM_RUNTIME_MODE", "legacy")
    with pytest.raises(HashEmbeddingForbiddenError, match="test-only"):
        assert_embedding_provider_allowed()


def test_hash_forbidden_in_published_mode_even_in_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("CM_EMBEDDING_PROVIDER", "hash")
    monkeypatch.setenv("CM_RUNTIME_MODE", "published")
    with pytest.raises(HashEmbeddingForbiddenError, match="CM_RUNTIME_MODE=published"):
        assert_embedding_provider_allowed()


@pytest.mark.asyncio
async def test_embed_texts_rejects_hash_in_published_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("CM_EMBEDDING_PROVIDER", "hash")
    monkeypatch.setenv("CM_RUNTIME_MODE", "published")
    with pytest.raises(HashEmbeddingForbiddenError):
        await embed_texts(["laser price"])


def test_published_embedding_pin_rejects_hash() -> None:
    with pytest.raises(PublishedEmbeddingError, match="hash"):
        assert_published_embedding_pin("hash", context="pointer")


@pytest.mark.asyncio
async def test_published_search_rejects_hash_index_manifest(monkeypatch: pytest.MonkeyPatch) -> None:
    """Index built with hash under legacy/test must not be searchable in published mode."""
    monkeypatch.setenv("CM_EMBEDDING_PROVIDER", "hash")
    monkeypatch.setenv("CM_RUNTIME_MODE", "legacy")
    monkeypatch.setenv("ENVIRONMENT", "test")
    tenant_id = "cm_embed_policy_hash_index"
    sections = {
        "faq": {
            "items": [
                {
                    "qa_group_id": "qa1",
                    "variants": [{"language": "en", "question": "price?", "answer": "20"}],
                    "tags": [],
                }
            ]
        },
        "knowledge": {"items": []},
        "care": {"items": []},
    }
    manifest = await build_index(
        tenant_id=tenant_id, content_version_id="v1", sections=sections, index_id="idx_hash_policy"
    )
    assert manifest["embedding"]["provider"] == "hash"

    monkeypatch.setenv("CM_RUNTIME_MODE", "published")
    with pytest.raises(PublishedEmbeddingError):
        await search(tenant_id=tenant_id, index_id="idx_hash_policy", query="price")


@pytest.mark.asyncio
async def test_published_mode_uses_openai_provider_end_to_end(monkeypatch: pytest.MonkeyPatch) -> None:
    install_mocked_openai_embeddings(monkeypatch, published_mode=True)
    tenant_id = "cm_embed_policy_openai"
    sections = {
        "faq": {
            "items": [
                {
                    "qa_group_id": "qa_price",
                    "variants": [
                        {
                            "language": "en",
                            "question": "What is the laser hair removal price?",
                            "answer": "20 USD",
                        }
                    ],
                    "tags": [],
                }
            ]
        },
        "knowledge": {"items": []},
        "care": {"items": []},
    }
    pin = embedding_pin()
    assert pin.provider == "openai"
    assert pin.model == "text-embedding-3-small"
    manifest = await build_index(
        tenant_id=tenant_id, content_version_id="v1", sections=sections, index_id="idx_openai_policy"
    )
    assert manifest["embedding"]["provider"] == "openai"
    hits = await search(
        tenant_id=tenant_id,
        index_id="idx_openai_policy",
        query="laser hair removal price",
        kind="faq",
        top_k=1,
    )
    assert hits
    assert hits[0]["source_id"].startswith("faq:")
