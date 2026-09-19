"""Hydrate hours/prices from published SoT. Opening-hours rows must not drop branch clocks."""

from __future__ import annotations

from services.brain.retrieve.cards import cards_from_sections
from services.brain.retrieve.hydrate import expand_hits
from services.brain.retrieve.lexical import LexicalHit, search_cards
from tests.brain_evals.qa_tenants import shop_a_qa_sections


def test_branch_hours_hydrate_when_opening_hours_exist() -> None:
    sections = shop_a_qa_sections()
    cards = cards_from_sections(sections, tenant_id="qa-shop-a")
    branch_hours = next(card for card in cards if card.item_id == "hours:antelias")
    bundle = expand_hits([LexicalHit(card=branch_hours, score=1.0)], sections, tenant_id="qa-shop-a")
    assert bundle.items
    text = bundle.items[0].text.lower()
    assert "11:00" in bundle.items[0].text
    assert "19:00" in bundle.items[0].text
    assert "sunday: closed" not in text
    assert "closed" not in text


def test_consultation_prices_keep_branch_amounts() -> None:
    sections = shop_a_qa_sections()
    cards = cards_from_sections(sections, tenant_id="qa-shop-a")
    consult = next(card for card in cards if card.item_id == "services:consultation")
    assert "80" in consult.search_text
    assert "70" in consult.search_text
    assert "beirut" in consult.search_text
    assert "antelias" in consult.search_text
    bundle = expand_hits([LexicalHit(card=consult, score=1.0)], sections, tenant_id="qa-shop-a")
    text = bundle.items[0].text.lower()
    assert "80" in text and "beirut" in text
    assert "70" in text and "antelias" in text
    hits = search_cards(cards, "سعر الاستشارة ببيروت", families={"services", "prices"})
    assert hits
    assert any(hit.card.item_id == "services:consultation" for hit in hits)


def test_consultation_media_urls_are_indexed() -> None:
    cards = cards_from_sections(shop_a_qa_sections(), tenant_id="qa-shop-a")
    blob = " ".join(card.search_text for card in cards)
    assert "consultation pictures" in blob
    assert "consultation looks" in blob
    assert "booking page" in blob
