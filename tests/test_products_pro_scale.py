"""Products pro-scale: no full-catalog load on customer turn; incremental reindex."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from services.brain.contracts.turn import CustomerTurn
from services.brain.providers.voyage_client import VoyageVectors
from services.brain.retrieve.hybrid import search_hybrid
from services.brain.retrieve.orchestrate import RetrieveContext, retrieve_published
from services.brain.search.store import reset_memory_store, write_documents
from services.products.image_match import match_product_image, voyage_multimodal_search_enabled
from services.products.reindex import delete_product_vectors, upsert_product_vectors

ROOT = Path(__file__).resolve().parents[1]
TURN_FILES = (
    "services/brain/retrieve/orchestrate.py",
    "services/brain/retrieve/hybrid.py",
    "services/brain/retrieve/catalog_list.py",
    "services/brain/retrieve/hydrate.py",
    "services/brain/tools/reads.py",
    "services/brain/agent/loop.py",
    "services/brain/agent/multi_retrieve.py",
    "services/brain/turn_pipeline.py",
    "services/brain/media/product_image_match.py",
    "services/products/image_index.py",
    "services/products/image_ann.py",
    "services/products/image_match.py",
)
LAYOUT_FILES = (
    "services/products/search_cards.py",
    "services/products/image_match.py",
    "services/products/image_index.py",
    "services/products/image_ann.py",
    "services/products/image_phash_vec.py",
    "services/products/reindex.py",
    "services/products/media_descriptors.py",
    "services/products/authorized_media.py",
    "services/brain/retrieve/products_hydrate.py",
    "services/brain/media/product_image_match.py",
    "services/brain/retrieve/hybrid.py",
    "services/brain/retrieve/orchestrate.py",
    "services/brain/retrieve/catalog_list.py",
    "services/products/service.py",
    "services/products/repository.py",
    "services/brain/reply/inbound_media_enrich.py",
)


def test_customer_turn_sources_do_not_list_all_products() -> None:
    hits: list[str] = []
    for rel in TURN_FILES:
        text = (ROOT / rel).read_text(encoding="utf-8")
        if "list_all_for_tenant" in text:
            hits.append(f"{rel}:list_all_for_tenant")
        if "load_product_cards(" in text:
            hits.append(f"{rel}:load_product_cards")
    assert not hits, hits


def test_new_product_modules_stay_under_400_lines() -> None:
    over: list[str] = []
    for rel in LAYOUT_FILES:
        path = ROOT / rel
        n = len(path.read_text(encoding="utf-8").splitlines())
        if n > 400:
            over.append(f"{rel}:{n}")
    assert not over, over


def test_readme_documents_save_publish_query_image() -> None:
    text = (ROOT / "services/products/README.md").read_text(encoding="utf-8")
    assert len(text.splitlines()) <= 80
    assert "Luna" in text
    assert "Voyage" in text
    assert "pHash" in text or "fingerprint" in text
    assert "Terra" in text


def test_multimodal_voyage_defaults_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LINAS_PRODUCT_MULTIMODAL_SEARCH", raising=False)
    assert voyage_multimodal_search_enabled() is False


@pytest.mark.asyncio
async def test_hybrid_hydrates_store_product_without_card_dump(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.brain.providers.spaces import ENTITY_DOCUMENT

    reset_memory_store()
    called = {"list_all": 0}

    def _boom(*_a: object, **_k: object) -> list:
        called["list_all"] += 1
        raise AssertionError("list_all_for_tenant on retrieve")

    async def fake_embed(space: object, texts: list[str]) -> VoyageVectors:
        return VoyageVectors(getattr(space, "space_id", "entity"), [[1.0, 0.0] for _ in texts])

    monkeypatch.setattr(
        "services.products.repository.ProductsRepository.list_all_for_tenant",
        _boom,
    )
    monkeypatch.setattr("services.products.search_cards.search_product_cards", lambda *_a, **_k: [])
    monkeypatch.setattr("services.brain.retrieve.hybrid.embed_texts", fake_embed)

    def _no_db(*_a: object, **_k: object) -> None:
        raise RuntimeError("no_db")

    monkeypatch.setattr("db.session.whatsapp_session", _no_db)
    write_documents(
        None,
        [
            {
                "id": "products:bag-1",
                "tenant_id": "shop",
                "space_id": ENTITY_DOCUMENT.space_id,
                "source_family": "products",
                "source_id": "bag-1",
                "title": "Leather Bag",
                "search_text": "Leather Bag brown tote",
                "visible": True,
            }
        ],
        [[1.0, 0.0]],
    )
    hits = await search_hybrid([], "leather bag", families={"products"}, tenant_id="shop")
    assert called["list_all"] == 0
    assert hits
    assert hits[0].card.item_id == "products:bag-1"


@pytest.mark.asyncio
async def test_retrieve_published_does_not_list_all(monkeypatch: pytest.MonkeyPatch) -> None:
    called = {"list_all": 0}

    def _boom(*_a: object, **_k: object) -> list:
        called["list_all"] += 1
        raise AssertionError("list_all_for_tenant on retrieve")

    monkeypatch.setattr("services.brain.retrieve.orchestrate.voyage_configured", lambda: True)
    monkeypatch.setattr("services.brain.search.product_freshness.product_questions_blocked", lambda *_a, **_k: None)
    monkeypatch.setattr(
        "services.brain.search.readiness.resolve_search_readiness",
        lambda _tid: SimpleNamespace(ready=True, reason="ok"),
    )
    monkeypatch.setattr(
        "services.brain.retrieve.orchestrate.load_published_content",
        lambda _tid: (SimpleNamespace(revision="r1"), {}),
    )
    monkeypatch.setattr("services.brain.retrieve.orchestrate.load_published_cards", lambda _tid: [])
    monkeypatch.setattr("services.products.repository.ProductsRepository.list_all_for_tenant", _boom)

    async def _hybrid(*_a: object, **_k: object) -> list:
        return []

    monkeypatch.setattr("services.brain.retrieve.orchestrate.search_hybrid", _hybrid)
    bundle = await retrieve_published(
        RetrieveContext(tenant_id="shop", query="cream", families={"products"}),
    )
    assert called["list_all"] == 0
    assert bundle.outcome in {"not_found", "found"}


@pytest.mark.asyncio
async def test_incremental_upsert_writes_one_product(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_memory_store()
    from services.brain.providers.spaces import ENTITY_DOCUMENT
    from services.brain.search.store import activate_pointer, query_similar

    activate_pointer(
        None,
        tenant_id="shop-up",
        space_id=ENTITY_DOCUMENT.space_id,
        source_family="entities",
        version="rev-1",
        count=1,
        source_revision="rev-1",
    )
    row = SimpleNamespace(
        id="p1",
        name="Night Cream",
        availability="in_stock",
        description="hydrate",
        note="",
        price="20",
        image_url="",
        product_url="",
        video_url="",
        ai_search_title="Night Cream",
        ai_search_description="hydrate",
        ai_search_keywords=[],
        updated_at="2026-01-01T00:00:00+00:00",
    )
    monkeypatch.setattr("services.products.reindex.voyage_configured", lambda: True)
    monkeypatch.setattr("services.products.reindex._load_row", lambda *_a, **_k: row)

    async def _embed(rows: list, *, session: object = None) -> tuple[list[list[float]], int]:
        _ = session
        return [[0.2, 0.1] for _ in rows], len(rows)

    monkeypatch.setattr("services.products.reindex.embed_document_rows_incremental", _embed)
    out = await upsert_product_vectors("shop-up", "p1", session=None)
    assert out.get("ok") is True
    hits = query_similar(
        None,
        tenant_id="shop-up",
        space_id=ENTITY_DOCUMENT.space_id,
        vector=[0.2, 0.1],
        families={"products"},
        limit=5,
    )
    assert any(hit.source_id == "p1" for hit in hits.items)
    deleted = delete_product_vectors(None, "shop-up", "p1")
    assert deleted.get("ok") is True
    after = query_similar(
        None,
        tenant_id="shop-up",
        space_id=ENTITY_DOCUMENT.space_id,
        vector=[0.2, 0.1],
        families={"products"},
        limit=5,
    )
    assert all(hit.source_id != "p1" for hit in after.items)


def test_low_score_image_match_is_not_high_confidence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "services.products.image_match.find_image_candidates",
        lambda *_a, **_k: [{"product_id": "p-low", "similarity": 0.2, "media_id": "m1"}],
    )

    class _Session:
        def __enter__(self) -> object:
            return self

        def __exit__(self, *_a: object) -> None:
            return None

    monkeypatch.setattr("db.session.whatsapp_session", lambda **_k: _Session())
    rows = match_product_image("t1", b"\xff\xd8\xff\xd9", min_score=0.0)
    assert rows
    assert rows[0]["product_id"] == "p-low"
    assert rows[0]["high_confidence"] is False


def test_high_score_image_match_injects_evidence_not_copy(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.brain.contracts.evidence import EvidenceBundle, EvidenceItem
    from services.brain.media.product_image_match import merge_product_image_evidence

    item = EvidenceItem(
        evidence_id="products:serum-1",
        source_family="products",
        source_id="serum-1",
        title="Vitamin C Serum",
        text="brightening",
        extra={"product_image_match": True},
    )
    monkeypatch.setattr(
        "services.brain.retrieve.products_hydrate.evidence_for_product_ids",
        lambda *_a, **_k: [item],
    )
    turn = CustomerTurn(
        tenant_id="t1",
        extra={"product_image_matches": [{"product_id": "serum-1", "score": 0.99}]},
    )
    bundle = merge_product_image_evidence(turn, EvidenceBundle(outcome="not_found"))
    assert bundle.outcome == "found"
    assert bundle.items[0].source_id == "serum-1"
    assert bundle.items[0].extra.get("product_image_match") is True
