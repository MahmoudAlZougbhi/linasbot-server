"""Qdrant store + tenant isolation tests (in-memory client)."""

from __future__ import annotations

import pytest
from qdrant_client import QdrantClient

from services.retrieval_index.pipeline import IndexPipeline
from services.retrieval_v2.errors import SearchStoreConfigError, SearchTenantRequiredError
from services.retrieval_v2.providers.fake_embeddings import FakeEmbeddingProvider
from services.retrieval_v2.schemas import SearchDocument, SourceType
from services.retrieval_v2.stores.qdrant_store import QdrantSearchStore


def _doc(tenant: str, source_id: str, text: str, *, active: bool = True) -> SearchDocument:
    return SearchDocument(
        tenant_id=tenant,
        source_type=SourceType.KNOWLEDGE,
        source_id=source_id,
        chunk_id="main",
        semantic_text=text,
        title="Premium laser",
        published_revision="r1",
        active=active,
    )


@pytest.fixture
def store() -> QdrantSearchStore:
    client = QdrantClient(location=":memory:")
    return QdrantSearchStore(client=client, collection="tenant_business_v2_test")


@pytest.mark.asyncio
async def test_collection_upsert_update_and_search(store: QdrantSearchStore) -> None:
    emb = FakeEmbeddingProvider(dimensions=32)
    doc = _doc("tenant-a", "k1", "Premium laser package includes six sessions.")
    vec = (await emb.embed_documents([doc.semantic_text], titles=[doc.title]))[0]
    ids1 = await store.upsert_documents(tenant_id="tenant-a", documents=[doc], vectors=[vec])
    assert len(ids1) == 1
    # Idempotent update same point
    doc2 = _doc("tenant-a", "k1", "Premium laser package includes six sessions. Updated note.")
    vec2 = (await emb.embed_documents([doc2.semantic_text], titles=[doc2.title]))[0]
    ids2 = await store.upsert_documents(tenant_id="tenant-a", documents=[doc2], vectors=[vec2])
    assert ids1 == ids2
    q = await emb.embed_query("laser package sessions")
    hits = await store.search_dense(tenant_id="tenant-a", query_vector=q, limit=5)
    assert hits
    assert hits[0].document.tenant_id == "tenant-a"
    assert "Updated note" in hits[0].document.semantic_text


@pytest.mark.asyncio
async def test_search_requires_tenant(store: QdrantSearchStore) -> None:
    with pytest.raises(SearchTenantRequiredError):
        await store.search_dense(tenant_id="", query_vector=[0.1] * 32)


@pytest.mark.asyncio
async def test_tenant_isolation_blocker(store: QdrantSearchStore) -> None:
    emb = FakeEmbeddingProvider(dimensions=32)
    text_a = "Premium laser package includes six sessions. Price for tenant A is 500."
    text_b = "Premium laser package includes six sessions. Price for tenant B is 999."
    doc_a = _doc("tenant-a", "same-title", text_a)
    doc_b = _doc("tenant-b", "same-title", text_b)
    va = (await emb.embed_documents([doc_a.semantic_text], titles=[doc_a.title]))[0]
    vb = (await emb.embed_documents([doc_b.semantic_text], titles=[doc_b.title]))[0]
    await store.upsert_documents(tenant_id="tenant-a", documents=[doc_a], vectors=[va])
    await store.upsert_documents(tenant_id="tenant-b", documents=[doc_b], vectors=[vb])

    q = await emb.embed_query("Premium laser package")
    hits_a = await store.search_dense(tenant_id="tenant-a", query_vector=q, limit=10)
    hits_b = await store.search_dense(tenant_id="tenant-b", query_vector=q, limit=10)

    assert hits_a
    assert all(h.document.tenant_id == "tenant-a" for h in hits_a)
    assert all("tenant A" in h.document.semantic_text for h in hits_a)
    assert hits_b
    assert all(h.document.tenant_id == "tenant-b" for h in hits_b)
    assert all("tenant B" in h.document.semantic_text for h in hits_b)
    assert not any("tenant B" in h.document.semantic_text for h in hits_a)
    assert not any("tenant A" in h.document.semantic_text for h in hits_b)


@pytest.mark.asyncio
async def test_active_filter_and_deactivate(store: QdrantSearchStore) -> None:
    emb = FakeEmbeddingProvider(dimensions=32)
    doc = _doc("tenant-a", "k-active", "Active knowledge about laser.")
    vec = (await emb.embed_documents([doc.semantic_text]))[0]
    point_ids = await store.upsert_documents(tenant_id="tenant-a", documents=[doc], vectors=[vec])
    q = await emb.embed_query("laser knowledge")
    assert await store.search_dense(tenant_id="tenant-a", query_vector=q, limit=5)
    await store.deactivate_documents(tenant_id="tenant-a", point_ids=point_ids)
    assert await store.search_dense(tenant_id="tenant-a", query_vector=q, limit=5) == []
    assert await store.search_dense(tenant_id="tenant-a", query_vector=q, limit=5, active_only=False)


@pytest.mark.asyncio
async def test_delete(store: QdrantSearchStore) -> None:
    emb = FakeEmbeddingProvider(dimensions=32)
    doc = _doc("tenant-a", "k-del", "Delete me laser text.")
    vec = (await emb.embed_documents([doc.semantic_text]))[0]
    point_ids = await store.upsert_documents(tenant_id="tenant-a", documents=[doc], vectors=[vec])
    await store.delete_documents(tenant_id="tenant-a", point_ids=point_ids)
    q = await emb.embed_query("Delete me laser")
    assert await store.search_dense(tenant_id="tenant-a", query_vector=q, limit=5, active_only=False) == []


@pytest.mark.asyncio
async def test_incompatible_dimensions(store: QdrantSearchStore) -> None:
    await store.ensure_collection(dimensions=32)
    with pytest.raises(SearchStoreConfigError, match="dim="):
        await store.ensure_collection(dimensions=64)


@pytest.mark.asyncio
async def test_pipeline_upsert_and_retrieve(store: QdrantSearchStore) -> None:
    emb = FakeEmbeddingProvider(dimensions=32)
    pipeline = IndexPipeline(embeddings=emb, store=store)
    doc = _doc("tenant-a", "pipe-1", "Premium laser package includes six sessions.")
    result = await pipeline.run_upsert(doc)
    assert result.status == "ok"
    assert result.point_ids
    assert result.embedding_dimensions == 32
    q = await emb.embed_query("six sessions laser")
    hits = await store.search_dense(tenant_id="tenant-a", query_vector=q, limit=3)
    assert hits
    assert hits[0].document.source_id == "pipe-1"


@pytest.mark.asyncio
async def test_smoke_two_tenants_same_title(store: QdrantSearchStore) -> None:
    """Integration smoke: index → embed → search tenant A, zero B leakage."""
    emb = FakeEmbeddingProvider(dimensions=32)
    pipeline = IndexPipeline(embeddings=emb, store=store)
    await pipeline.run_upsert(
        _doc("tenant-a", "knowledge-1", "Premium laser package includes six sessions.")
    )
    await pipeline.run_upsert(
        _doc("tenant-b", "knowledge-1", "Premium laser package includes six sessions. Tenant B secret price 777.")
    )
    q = await emb.embed_query("Premium laser package includes six sessions")
    hits = await store.search_dense(tenant_id="tenant-a", query_vector=q, limit=5)
    assert hits
    assert hits[0].document.tenant_id == "tenant-a"
    assert all(h.document.tenant_id == "tenant-a" for h in hits)
    assert not any("Tenant B secret" in h.document.semantic_text for h in hits)
    health = await store.health_check()
    assert health["status"] == "ok"
    assert health["dimensions"] == 32
