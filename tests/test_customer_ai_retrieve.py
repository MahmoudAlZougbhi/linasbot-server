"""Retrieve, products adapter, heuristic planner, and grounding."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from services.customer_ai.contracts.evidence import EvidenceBundle, EvidenceItem
from services.customer_ai.grounding.facts import evidence_supports_text, ungrounded_amounts
from services.customer_ai.planner.heuristic import plan_message
from services.customer_ai.providers.voyage_client import VoyageVectors
from services.customer_ai.retrieve.cards import cards_from_sections
from services.customer_ai.retrieve.expand import expand_hits
from services.customer_ai.retrieve.lexical import LexicalHit
from services.customer_ai.retrieve.hybrid import search_hybrid
from services.customer_ai.retrieve.orchestrate import retrieve_cards
from services.customer_ai.retrieve.products import cards_from_products, evidence_from_product


def test_inactive_products_are_not_searchable() -> None:
    rows = [
        SimpleNamespace(
            id="hidden",
            name="Hidden Serum",
            availability="inactive",
            ai_search_title="Hidden Serum",
            ai_search_description="do not show",
            ai_search_keywords=["serum"],
            description="secret",
            note="",
            price="10",
            updated_at="2026-01-01T00:00:00+00:00",
        ),
        SimpleNamespace(
            id="vis",
            name="Visible Cream",
            availability="in_stock",
            ai_search_title="Visible Cream",
            ai_search_description="face cream",
            ai_search_keywords=["cream"],
            description="hydrating",
            note="",
            price="12 USD",
            updated_at="2026-01-02T00:00:00+00:00",
        ),
    ]
    cards = cards_from_products(rows)
    assert [c.item_id for c in cards] == ["products:vis"]
    item = evidence_from_product(rows[1])
    assert item is not None
    assert item.revision == "2026-01-02T00:00:00+00:00"
    assert "12 USD" in item.text
    assert evidence_from_product(rows[0]) is None


def test_hours_cards_expand_weekday_lines() -> None:
    sections = {
        "opening_hours": {
            "items": [
                {
                    "id": "main",
                    "title": "Main branch hours",
                    "monday": {"open": "10:00", "close": "20:00"},
                    "sunday": {"closed": True},
                }
            ]
        }
    }
    cards = cards_from_sections(sections)
    assert cards[0].item_id == "hours:main"
    bundle = expand_hits([LexicalHit(card=cards[0], score=1.0)], sections)
    assert "monday: 10:00–20:00" in bundle.items[0].text
    assert "sunday: closed" in bundle.items[0].text


def test_heuristic_plan_does_not_hard_route_one_source() -> None:
    plan = plan_message("بدي سعر الليزر وساعات الفرع")
    families = {fam for task in plan.tasks for fam in task.source_families}
    assert "services" in families
    assert "hours" in families
    assert plan.read_only is True
    action = plan_message("I want to book laser and talk to a human")
    assert action.read_only is False
    assert {t.type for t in action.tasks} >= {"service_request", "human_request"}


def test_grounding_rejects_invented_price() -> None:
    bundle = EvidenceBundle(
        items=[
            EvidenceItem(
                evidence_id="services:hair",
                source_family="services",
                source_id="hair",
                text="Hair Removal\n99.0 USD / session",
            )
        ]
    )
    assert ungrounded_amounts("Hair removal is 250 USD", bundle) == ["250|usd"]
    assert evidence_supports_text("Hair removal is 99.0 USD", bundle) is True


@pytest.mark.asyncio
async def test_retrieve_without_voyage_is_typed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VOYAGE_API_KEY", "")
    sections = {"prices": {"catalog": [{"id": "hair", "labels": {"en": "Hair Removal"}, "active": True}]}}
    bundle = await retrieve_cards(cards_from_sections(sections), "hair removal", sections=sections)
    assert bundle.outcome == "provider_not_configured"
    assert bundle.items == []


@pytest.mark.asyncio
async def test_hybrid_mocked_ranks_hair_over_botox(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_embed(space, texts):
        if space.input_mode == "query":
            return VoyageVectors(space.space_id, [[1.0, 0.0]])
        vectors = []
        for text in texts:
            lowered = text.lower()
            vectors.append([0.95, 0.05] if "hair" in lowered or "شعر" in lowered else [0.05, 0.95])
        return VoyageVectors(space.space_id, vectors)

    monkeypatch.setattr("services.customer_ai.retrieve.hybrid.embed_texts", fake_embed)
    sections = {
        "prices": {
            "catalog": [
                {"id": "hair", "labels": {"en": "Hair Removal"}, "aliases": ["lazer"], "active": True},
                {"id": "botox", "labels": {"en": "Botox"}, "active": True},
            ]
        }
    }
    hits = await search_hybrid(cards_from_sections(sections), "بدي hair removal", families={"services"}, limit=2)
    assert hits[0].card.item_id == "services:hair"
