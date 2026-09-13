"""Hydrate hours/prices from published SoT. Opening-hours rows must not drop branch clocks."""

from __future__ import annotations

from services.customer_ai.evals.qa_tenants import linas_like_qa_sections
from services.customer_ai.retrieve.cards import cards_from_sections
from services.customer_ai.retrieve.expand import expand_hits
from services.customer_ai.retrieve.lexical import LexicalHit, search_cards


def test_branch_hours_hydrate_when_opening_hours_exist() -> None:
    sections = linas_like_qa_sections()
    cards = cards_from_sections(sections, tenant_id="qa-linas")
    branch_hours = next(card for card in cards if card.item_id == "hours:antelias")
    bundle = expand_hits([LexicalHit(card=branch_hours, score=1.0)], sections, tenant_id="qa-linas")
    assert bundle.items
    text = bundle.items[0].text.lower()
    assert "11:00" in bundle.items[0].text
    assert "19:00" in bundle.items[0].text
    assert "sunday: closed" not in text
    assert "closed" not in text


def test_laser_prices_keep_branch_amounts() -> None:
    sections = linas_like_qa_sections()
    cards = cards_from_sections(sections, tenant_id="qa-linas")
    laser = next(card for card in cards if card.item_id == "services:laser")
    assert "80" in laser.search_text
    assert "70" in laser.search_text
    assert "beirut" in laser.search_text
    assert "antelias" in laser.search_text
    bundle = expand_hits([LexicalHit(card=laser, score=1.0)], sections, tenant_id="qa-linas")
    text = bundle.items[0].text.lower()
    assert "80" in text and "beirut" in text
    assert "70" in text and "antelias" in text
    hits = search_cards(cards, "سعر الليزر ببيروت", families={"services", "prices"})
    assert hits
    assert any(hit.card.item_id == "services:laser" for hit in hits)


def test_laser_media_urls_are_indexed() -> None:
    cards = cards_from_sections(linas_like_qa_sections(), tenant_id="qa-linas")
    blob = " ".join(card.search_text for card in cards)
    assert "qa linas example" in blob
    assert "laser women" in blob
    assert "laser session" in blob
    assert "book laser" in blob or "book" in blob
