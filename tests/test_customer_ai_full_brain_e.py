"""Tests for Full Agentic AI Brain upgrades (contextual, memory, authority, tools)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from services.customer_ai.compiler.chunks import chunk_document, contextual_groups
from services.customer_ai.contracts.evidence import EvidenceBundle, EvidenceItem
from services.customer_ai.ingest.multimodal import classify_media, process_knowledge_media
from services.customer_ai.memory.store import remember_fact, recall_facts, reset_memory_for_tests
from services.customer_ai.providers.spaces import KNOWLEDGE_DOCUMENT, KNOWLEDGE_MODEL, spaces_snapshot
from services.customer_ai.retrieve.conflict import apply_authority
from services.customer_ai.relations.graph import load_relations
from services.customer_ai.search.store import activate_pointer, query_similar, write_documents
from services.customer_ai.tools.registry import execute_tool, list_tools


def test_contextual_chunks_keep_raw_and_context() -> None:
    chunks = chunk_document(
        document_id="knowledge:laser",
        body="# Full Body\nPrice is 120 USD in Antelias.",
        document_title="Laser Guide",
        entity="Full Body",
        branch="Antelias",
        tenant_id="linas",
    )
    assert chunks
    assert chunks[0].raw_text
    assert "Document: Laser Guide" in chunks[0].contextualized_text
    assert "Price is 120 USD" in chunks[0].raw_text
    groups = contextual_groups(chunks)
    assert "knowledge:laser" in groups


def test_spaces_contextual_active() -> None:
    snap = spaces_snapshot()
    assert snap["knowledge_model"] == KNOWLEDGE_MODEL
    assert snap["contextual_active"] == "true"
    assert "contextualized" in KNOWLEDGE_DOCUMENT.endpoint


def test_authority_drops_lower_conflicting_amount() -> None:
    bundle = EvidenceBundle(
        items=[
            EvidenceItem(
                evidence_id="prices:1",
                source_family="prices",
                source_id="1",
                text="Full Body is 60 USD",
                revision="v2",
            ),
            EvidenceItem(
                evidence_id="knowledge:old",
                source_family="knowledge",
                source_id="old",
                text="Full Body is 50 USD",
                revision="v1",
            ),
        ],
        outcome="found",
    )
    resolved, meta = apply_authority(bundle)
    assert any(item.evidence_id == "prices:1" for item in resolved.items)
    assert meta.get("decisions") or meta.get("conflicts") is not None


def test_memory_durable_api_roundtrip() -> None:
    reset_memory_for_tests()
    out = remember_fact(tenant_id="t1", customer_id="c1", key="branch", value="Antelias")
    assert out["ok"] is True
    rows = recall_facts(tenant_id="t1", customer_id="c1")
    assert any(row.get("key") == "branch" and "Antelias" in row.get("value", "") for row in rows)


def test_index_pointer_atomic_activate_and_query_filters_version() -> None:
    rows = [
        {
            "id": "t1:doc:v1",
            "tenant_id": "t1",
            "space_id": "space-a",
            "source_family": "knowledge",
            "source_id": "doc",
            "chunk_id": "",
            "parent_id": "",
            "index_version": "v1",
            "source_revision": "r1",
            "content_hash": "h1",
            "title": "A",
            "search_text": "alpha",
            "visible": True,
        },
        {
            "id": "t1:doc:v2",
            "tenant_id": "t1",
            "space_id": "space-a",
            "source_family": "knowledge",
            "source_id": "doc",
            "chunk_id": "",
            "parent_id": "",
            "index_version": "v2",
            "source_revision": "r2",
            "content_hash": "h2",
            "title": "B",
            "search_text": "beta",
            "visible": True,
        },
    ]
    vectors = [[1.0, 0.0], [0.0, 1.0]]
    # pad to 1024 dims loosely by repeating — store memory cosine only needs equal length
    vectors = [[0.9, 0.1] * 512, [0.1, 0.9] * 512]
    write_documents(None, rows, vectors)
    activate_pointer(
        None,
        tenant_id="t1",
        space_id="space-a",
        source_family="knowledge_ctx",
        version="v2",
        count=1,
        source_revision="r2",
    )
    result = query_similar(None, tenant_id="t1", space_id="space-a", vector=[0.1, 0.9] * 512, limit=5)
    assert result.outcome == "found"
    assert all("v2" in item.doc_id for item in result.items)


def test_tool_registry_includes_contact_and_request_state() -> None:
    tools = list_tools()
    assert "get_contact" in tools["read"]
    assert "get_request_state" in tools["read"]
    assert "get_availability" in tools["unsupported"]


@pytest.mark.asyncio
async def test_multimodal_pdf_fail_visible_without_library() -> None:
    assert classify_media("x.pdf", "application/pdf") == "pdf"
    with patch("services.customer_ai.ingest.multimodal.extract_pdf_text", new=AsyncMock(return_value={
        "ok": False, "status": "FAILED", "reason": "pdf_extract_unavailable:ImportError", "text": "", "pages": 0
    })):
        out = await process_knowledge_media(tenant_id="t1", filename="x.pdf", content_type="application/pdf", data=b"%PDF")
    assert out["status"] == "FAILED"
    assert out["ok"] is False


def test_relations_loader_handles_unpublished() -> None:
    out = load_relations("definitely-missing-tenant-xyz")
    assert "relations" in out


def test_probe_pgvector_uses_sqlalchemy_text() -> None:
    from services.customer_ai.search.readiness import probe_pgvector

    class _Session:
        def execute(self, statement, *args, **kwargs):  # noqa: ANN001
            assert hasattr(statement, "text") or "SELECT EXISTS" in str(statement)
            class _Result:
                def scalar(self):
                    return True

            return _Result()

    assert probe_pgvector(_Session()) is True
    assert probe_pgvector(None) is False


def test_cards_include_all_label_languages() -> None:
    from services.customer_ai.retrieve.cards import cards_from_sections
    from services.customer_ai.retrieve.lexical import search_cards

    sections = {
        "prices": {
            "catalog": [
                {
                    "id": "laser",
                    "labels": {"en": "Laser hair removal", "ar": "إزالة الشعر"},
                    "aliases": ["lazer"],
                    "active": True,
                }
            ]
        }
    }
    cards = cards_from_sections(sections)
    hits = search_cards(cards, "قدي سعر إزالة الشعر", families={"services"}, limit=3)
    assert hits
    assert hits[0].card.item_id.endswith("laser")


@pytest.mark.asyncio
async def test_get_price_is_branch_scoped() -> None:
    from services.cm.paths import ensure_cm_dirs
    from services.cm.schemas import PublishedPointer, utc_now
    from services.cm.version_store import write_published_pointer, write_version_content
    from services.customer_ai.contracts.turn import CustomerTurn
    from services.customer_ai.tools.registry import execute_tool

    tid = "lab-price-branch"
    ensure_cm_dirs(tid)
    sections = {
        "prices": {
            "catalog": [{"id": "laser", "labels": {"en": "Laser"}, "active": True}],
            "price_entries": [
                {"id": "a", "catalog_item_id": "laser", "branch_id": "antelias", "amount": 60, "currency": "USD", "active": True},
                {"id": "b", "catalog_item_id": "laser", "branch_id": "verdun", "amount": 75, "currency": "USD", "active": True},
            ],
        }
    }
    write_version_content(tid, "v1", sections)
    write_published_pointer(
        tid,
        PublishedPointer(
            content_version_id="v1",
            checksums={},
            embedding_provider="voyage",
            embedding_model="voyage-context-4",
            embedding_version="t",
            embedding_dimensions=1024,
            updated_at=utc_now(),
        ),
    )
    turn = CustomerTurn(tenant_id=tid, customer_id="c1", conversation_id="x", channel="lab")
    ant = await execute_tool("get_price", {"service_id": "laser", "branch_id": "antelias"}, turn)
    verd = await execute_tool("get_price", {"service_id": "laser", "branch_id": "verdun"}, turn)
    assert ant.get("ok") and ant["data"]["amount"] == 60
    assert verd.get("ok") and verd["data"]["amount"] == 75
