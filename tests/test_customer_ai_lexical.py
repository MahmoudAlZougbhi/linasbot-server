"""Lexical title-card search is Okapi BM25 and does not dump the catalog."""

from __future__ import annotations

import pytest

from services.customer_ai.retrieve.cards import TitleCard, cards_from_sections
from services.customer_ai.retrieve.expand import expand_hits
from services.customer_ai.retrieve.lexical import BM25_K1, bm25_scores, search_cards, tokenize


def test_lexical_finds_hair_removal_only() -> None:
    sections = {
        "services": {
            "items": [
                {
                    "id": "hair",
                    "labels": {"en": "Hair Removal", "ar": "إزالة الشعر"},
                    "aliases": ["lazer", "laser"],
                    "ai_search_title": "Laser hair removal",
                },
                {
                    "id": "bots",
                    "labels": {"en": "Botox"},
                    "ai_search_title": "Botox injection",
                },
            ]
        },
        "knowledge": {
            "items": [
                {
                    "id": "aftercare",
                    "title": "Laser aftercare",
                    "ai_search_description": "what to do after laser",
                }
            ]
        },
    }
    cards = cards_from_sections(sections, revision="1")
    hits = search_cards(cards, "بدي hair removal", families={"services"}, limit=5)
    assert hits
    assert hits[0].card.item_id == "services:hair"
    assert all(hit.card.source_family == "services" for hit in hits)


def test_knowledge_body_absent_from_title_still_has_search_description() -> None:
    sections = {
        "knowledge": {
            "items": [
                {
                    "id": "doc1",
                    "title": "Clinic booklet",
                    "ai_search_description": "refund policy after seven days",
                }
            ]
        }
    }
    hits = search_cards(cards_from_sections(sections), "refund policy")
    assert hits[0].card.item_id == "knowledge:doc1"


def test_mobile_services_catalog_is_prices_not_legacy_services() -> None:
    sections = {
        "services": {"items": [{"id": "legacy", "labels": {"en": "Hair Removal"}, "notes": "old"}]},
        "prices": {
            "catalog": [
                {
                    "id": "hair",
                    "labels": {"en": "Hair Removal", "ar": "إزالة الشعر"},
                    "aliases": ["lazer"],
                    "description": "full body laser",
                    "base_price": 80,
                    "currency": "USD",
                    "active": True,
                }
            ],
            "price_entries": [
                {
                    "id": "e1",
                    "catalog_item_id": "hair",
                    "amount": 99,
                    "currency": "USD",
                    "unit": "session",
                    "active": True,
                }
            ],
        },
    }
    hits = search_cards(cards_from_sections(sections), "hair removal", families={"services"})
    assert hits[0].card.item_id == "services:hair"
    bundle = expand_hits(hits, sections)
    assert "99.0 USD / session" in bundle.items[0].text
    assert "old" not in bundle.items[0].text


def test_expand_loads_only_winner_full_text() -> None:
    sections = {
        "knowledge": {
            "items": [
                {"id": "a", "title": "A", "body": "alpha secret", "ai_search_description": "alpha"},
                {"id": "b", "title": "B", "body": "beta secret", "ai_search_description": "beta"},
            ]
        }
    }
    hits = search_cards(cards_from_sections(sections), "alpha")
    bundle = expand_hits(hits, sections, revision="r1")
    assert bundle.outcome == "found"
    assert [item.source_id for item in bundle.items] == ["a"]
    assert "alpha secret" in bundle.items[0].text
    assert "beta secret" not in bundle.items[0].text


def _card(item_id: str, search_text: str) -> TitleCard:
    return TitleCard(
        item_id=f"services:{item_id}",
        source_family="services",
        title=item_id,
        search_text=search_text,
    )


def test_bm25_weights_rare_terms_above_common_terms() -> None:
    common = ["laser session"] * 8
    documents = [tokenize(text) for text in [*common, "laser peeling"]]
    scores = bm25_scores(tokenize("laser peeling"), documents)
    # "laser" is in every document, "peeling" in one: the rare term must dominate.
    assert scores[-1] > max(scores[:-1])


def test_bm25_saturates_repeated_terms() -> None:
    once = bm25_scores(tokenize("laser"), [tokenize("laser"), tokenize("laser laser laser laser")])
    assert once[1] > once[0] * 0.5
    # Four occurrences are worth far less than four times one occurrence (k1 saturation).
    assert once[1] < once[0] * (BM25_K1 + 1.0)


def test_bm25_normalizes_document_length() -> None:
    short = "laser removal"
    long = "laser removal " + " ".join(f"filler{index}" for index in range(60))
    hits = search_cards([_card("short", short), _card("long", long)], "laser removal")
    assert [hit.card.item_id for hit in hits] == ["services:short", "services:long"]
    assert hits[0].score > hits[1].score


def test_bm25_is_not_substring_matching() -> None:
    # Old toy scorer gave a flat 0.85 to any substring containment; BM25 ranks by term evidence.
    focused = _card("focused", "laser hair removal price")
    padded = _card("padded", "gift card terms laser hair removal price " + " ".join(["policy"] * 40))
    hits = search_cards([padded, focused], "laser hair removal price")
    assert hits[0].card.item_id == "services:focused"
    # Scores are unbounded sums of per-term contributions, not a 0..1 similarity.
    assert hits[0].score > 1.0


def test_bm25_does_not_dump_unrelated_cards() -> None:
    hits = search_cards([_card("hair", "laser hair removal"), _card("gift", "gift card terms")], "laser")
    assert [hit.card.item_id for hit in hits] == ["services:hair"]
    assert search_cards([_card("hair", "laser hair removal")], "") == []
    assert search_cards([], "laser") == []


def test_bm25_respects_family_scope_and_limit() -> None:
    cards = [
        _card("a", "laser package one"),
        _card("b", "laser package two"),
        TitleCard(item_id="faq:f1", source_family="faq", title="F", search_text="laser package faq"),
    ]
    assert len(search_cards(cards, "laser package", limit=2)) == 2
    scoped = search_cards(cards, "laser package", families={"faq"})
    assert [hit.card.item_id for hit in scoped] == ["faq:f1"]


@pytest.mark.asyncio
async def test_hybrid_still_fuses_bm25_ranks_with_rrf() -> None:
    from services.customer_ai.retrieve.hybrid import search_hybrid

    cards = [_card("gift", "gift card terms"), _card("hair", "laser hair removal")]
    hits = await search_hybrid(cards, "laser hair removal", families={"services"})
    assert [hit.card.item_id for hit in hits] == ["services:hair"]
    assert hits[0].fused_rank == 0
    assert hits[0].lexical_score > 0
    assert hits[0].semantic_score == 0.0


def test_rerank_skip_uses_surface_equality_not_score_scale() -> None:
    from services.customer_ai.retrieve.hybrid import HybridHit
    from services.customer_ai.retrieve.rerank import should_rerank

    exact = _card("hair", "laser")
    other = _card("gift", "laser gift card")
    hits = [
        HybridHit(card=exact, lexical_score=2.7, semantic_score=0.0, fused_rank=0),
        HybridHit(card=other, lexical_score=1.1, semantic_score=0.0, fused_rank=1),
    ]
    assert should_rerank(hits, "laser") is False
    assert should_rerank(hits, "laser gift") is True
