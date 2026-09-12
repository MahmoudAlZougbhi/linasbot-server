"""SearchDocument / point-id validation tests."""

from __future__ import annotations

import pytest

from services.retrieval_v2.config import INDEX_SCHEMA_VERSION, retrieval_v2_enabled, retrieval_v2_shadow_enabled
from services.retrieval_v2.errors import RetrievalV2ValidationError
from services.retrieval_v2.schemas import SearchDocument, SourceType, document_point_id


def test_flags_default_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RETRIEVAL_V2_ENABLED", raising=False)
    monkeypatch.delenv("RETRIEVAL_V2_SHADOW", raising=False)
    assert retrieval_v2_enabled() is False
    assert retrieval_v2_shadow_enabled() is False


def test_search_document_requires_tenant_and_source() -> None:
    with pytest.raises(RetrievalV2ValidationError, match="tenant_id"):
        SearchDocument(
            tenant_id="",
            source_type=SourceType.KNOWLEDGE,
            source_id="k1",
            chunk_id="c1",
            semantic_text="hello",
        )
    with pytest.raises(RetrievalV2ValidationError, match="source_id"):
        SearchDocument(
            tenant_id="t1",
            source_type=SourceType.KNOWLEDGE,
            source_id=" ",
            chunk_id="c1",
            semantic_text="hello",
        )


def test_empty_semantic_text_rejected() -> None:
    with pytest.raises(RetrievalV2ValidationError, match="semantic_text"):
        SearchDocument(
            tenant_id="t1",
            source_type=SourceType.KNOWLEDGE,
            source_id="k1",
            chunk_id="c1",
            semantic_text="  ",
        )


def test_version_and_checksum_fields() -> None:
    doc = SearchDocument(
        tenant_id="t1",
        source_type=SourceType.KNOWLEDGE,
        source_id="k1",
        chunk_id="c1",
        semantic_text="Premium laser package includes six sessions.",
        published_revision="rev-1",
        source_version="sv-1",
    )
    assert doc.content_sha256
    assert doc.index_schema_version == INDEX_SCHEMA_VERSION
    assert doc.updated_at
    assert doc.published_revision == "rev-1"


def test_deterministic_point_id_stable() -> None:
    a = document_point_id(
        tenant_id="tenant-a",
        source_type=SourceType.KNOWLEDGE,
        source_id="art-1",
        chunk_id="main",
    )
    b = document_point_id(
        tenant_id="tenant-a",
        source_type=SourceType.KNOWLEDGE,
        source_id="art-1",
        chunk_id="main",
    )
    c = document_point_id(
        tenant_id="tenant-b",
        source_type=SourceType.KNOWLEDGE,
        source_id="art-1",
        chunk_id="main",
    )
    assert a == b
    assert a != c
    assert a.count("-") == 4
