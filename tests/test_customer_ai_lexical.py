"""Lexical title-card search does not dump the catalog."""

from __future__ import annotations

from services.customer_ai.retrieve.cards import cards_from_sections
from services.customer_ai.retrieve.expand import expand_hits
from services.customer_ai.retrieve.lexical import search_cards


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
