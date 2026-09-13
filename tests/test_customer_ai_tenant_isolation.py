"""Cross-tenant isolation for cards, products, and the in-memory search store."""

from __future__ import annotations

from services.customer_ai.evals.qa_tenants import (
    linas_like_products,
    linas_like_qa_sections,
    shop_b_products,
    shop_b_qa_sections,
)
from services.customer_ai.retrieve.cards import cards_from_sections
from services.customer_ai.retrieve.lexical import search_cards
from services.customer_ai.retrieve.products import cards_from_products
from services.customer_ai.search.store import query_similar, reset_memory_store, write_documents


def test_same_product_name_keeps_tenant_prices() -> None:
    linas = cards_from_products(linas_like_products())
    other = cards_from_products(shop_b_products())
    linas_alpha = next(card for card in linas if "alpha" in card.item_id.lower() or "alpha" in card.title.lower())
    other_alpha = next(card for card in other if "alpha" in card.item_id.lower() or "alpha" in card.title.lower())
    assert "10" in linas_alpha.search_text or "10" in linas_alpha.body
    assert "99" in other_alpha.search_text or "99" in other_alpha.body
    assert "99" not in linas_alpha.search_text
    assert "10" not in other_alpha.search_text


def test_hours_lexical_does_not_prefer_greeting_policy() -> None:
    cards = cards_from_sections(linas_like_qa_sections(), tenant_id="qa-linas")
    hits = search_cards(cards, "شو ساعات أنطلياس؟", families={"hours", "branches"})
    assert hits
    assert hits[0].card.source_family in {"hours", "branches"}
    assert "11 00" in hits[0].card.search_text or "antelias" in hits[0].card.item_id.lower()
    knowledge_ids = {card.item_id for card in cards if card.source_family == "knowledge"}
    assert hits[0].card.item_id not in knowledge_ids


def test_memory_store_same_doc_id_does_not_cross_tenants() -> None:
    reset_memory_store()
    vec_a = [1.0, 0.0, 0.0]
    vec_b = [0.0, 1.0, 0.0]
    row_a = {
        "id": "products:alpha",
        "tenant_id": "qa-linas",
        "space_id": "entity",
        "source_family": "products",
        "source_id": "alpha",
        "chunk_id": "0",
        "parent_id": "",
        "index_version": "v1",
        "source_revision": "r1",
        "content_hash": "a",
        "title": "Product Alpha",
        "search_text": "Product Alpha 10 USD",
        "visible": True,
    }
    row_b = {
        **row_a,
        "tenant_id": "qa-shop-b",
        "content_hash": "b",
        "search_text": "Product Alpha 99 USD",
    }
    assert write_documents(None, [row_a], [vec_a])["ok"] is True
    assert write_documents(None, [row_b], [vec_b])["ok"] is True
    hit_a = query_similar(None, tenant_id="qa-linas", space_id="entity", vector=vec_a, families={"products"}, limit=5)
    hit_b = query_similar(None, tenant_id="qa-shop-b", space_id="entity", vector=vec_b, families={"products"}, limit=5)
    texts_a = " ".join(item.search_text for item in hit_a.items)
    texts_b = " ".join(item.search_text for item in hit_b.items)
    assert "10 USD" in texts_a
    assert "99 USD" not in texts_a
    assert "99 USD" in texts_b
    assert "10 USD" not in texts_b
    assert all(item.tenant_id == "qa-linas" for item in hit_a.items)
    assert all(item.tenant_id == "qa-shop-b" for item in hit_b.items)


def test_product_media_urls_stay_on_own_tenant() -> None:
    from services.customer_ai.retrieve.products import evidence_from_product

    linas = cards_from_products(linas_like_products())
    other = cards_from_products(shop_b_products())
    linas_ev = " ".join(
        str(evidence_from_product(row).text) for row in linas_like_products() if evidence_from_product(row)
    )
    other_ev = " ".join(str(evidence_from_product(row).text) for row in shop_b_products() if evidence_from_product(row))
    assert linas
    assert other
    assert "qa.linas.example/aftercare.png" in linas_ev
    assert "qa.linas.example" not in other_ev
    assert "qa.shopb.example/alpha.png" in other_ev
    assert "qa.shopb.example" not in linas_ev
    linas_ids = {card.item_id for card in cards_from_sections(linas_like_qa_sections(), tenant_id="qa-linas")}
    other_ids = {card.item_id for card in cards_from_sections(shop_b_qa_sections(), tenant_id="qa-shop-b")}
    assert any("antelias" in item_id for item_id in linas_ids)
    assert not any("antelias" in item_id for item_id in other_ids)
    assert any("hamra" in item_id for item_id in other_ids)
