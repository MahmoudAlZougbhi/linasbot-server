"""Incremental Voyage embed reuses vectors when content_hash is unchanged."""

from __future__ import annotations

import pytest

from services.customer_ai.providers.voyage_client import VoyageVectors
from services.customer_ai.retrieve.cards import TitleCard
from services.customer_ai.search.index_job import document_rows, embed_document_rows_incremental
from services.customer_ai.search.store import reset_memory_store, write_documents


@pytest.mark.asyncio
async def test_unchanged_content_hash_skips_voyage(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_memory_store()
    calls = {"n": 0}

    async def _texts(_space: object, texts: list[str]) -> VoyageVectors:
        calls["n"] += len(texts)
        return VoyageVectors(space_id="entity", vectors=[[0.1, 0.2, 0.3, 0.0] for _ in texts])

    monkeypatch.setattr("services.customer_ai.search.index_job.voyage_configured", lambda: True)
    monkeypatch.setattr("services.customer_ai.search.index_job.embed_texts", _texts)

    card = TitleCard(
        item_id="knowledge:svc1",
        source_family="services",
        title="Laser",
        search_text="underarm laser",
        body="underarm laser",
        revision="r1",
    )
    rows_v1 = document_rows([card], tenant_id="shop-a", version="v1")
    vectors_v1, embedded_v1 = await embed_document_rows_incremental(rows_v1, session=None)
    write_documents(None, rows_v1, vectors_v1)
    assert embedded_v1 == 1
    assert calls["n"] == 1

    rows_v2 = document_rows([card], tenant_id="shop-a", version="v2")
    vectors_v2, embedded_v2 = await embed_document_rows_incremental(rows_v2, session=None)
    assert embedded_v2 == 0
    assert calls["n"] == 1
    assert vectors_v2 == vectors_v1


@pytest.mark.asyncio
async def test_changed_content_hash_reembeds(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_memory_store()
    calls: list[str] = []

    async def _texts(_space: object, texts: list[str]) -> VoyageVectors:
        calls.extend(texts)
        return VoyageVectors(space_id="entity", vectors=[[0.4, 0.1, 0.0, 0.0] for _ in texts])

    monkeypatch.setattr("services.customer_ai.search.index_job.voyage_configured", lambda: True)
    monkeypatch.setattr("services.customer_ai.search.index_job.embed_texts", _texts)

    first = TitleCard(
        item_id="knowledge:svc1",
        source_family="services",
        title="Laser",
        search_text="underarm laser",
        body="underarm laser",
        revision="r1",
    )
    rows_v1 = document_rows([first], tenant_id="shop-b", version="v1")
    vectors_v1, _ = await embed_document_rows_incremental(rows_v1, session=None)
    write_documents(None, rows_v1, vectors_v1)

    changed = TitleCard(
        item_id="knowledge:svc1",
        source_family="services",
        title="Laser",
        search_text="full body laser",
        body="full body laser",
        revision="r2",
    )
    rows_v2 = document_rows([changed], tenant_id="shop-b", version="v2")
    _vectors_v2, embedded_v2 = await embed_document_rows_incremental(rows_v2, session=None)
    assert embedded_v2 == 1
    assert calls[-1] == "full body laser"
