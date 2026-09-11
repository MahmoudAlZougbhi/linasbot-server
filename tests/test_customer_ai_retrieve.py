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


def test_heuristic_negation_reference_and_correction() -> None:
    asking = plan_message("Don't book, just asking the hours")
    assert "service_request" not in {task.type for task in asking.tasks}
    assert any(task.type == "hours" for task in asking.tasks)
    no_human = plan_message("I do not want a human, what is the serum price?")
    assert "human_request" not in {task.type for task in no_human.tasks}
    ref = plan_message("how much is the first one?")
    assert any("anaphor" in task.entity_mentions for task in ref.tasks)
    fix = plan_message("I meant the facial not the laser")
    assert any(task.type == "draft_correction" for task in fix.tasks)
    multi = plan_message("What is the price? What are the hours?")
    assert len([task for task in multi.tasks if task.type == "information"]) >= 2


def test_branch_weekly_hours_hydrate() -> None:
    sections = {
        "branches": {
            "items": [
                {
                    "id": "beirut",
                    "title": "Beirut",
                    "weekly_hours": {
                        "monday": {"open": "09:00", "close": "17:00"},
                        "sunday": {"closed": True},
                    },
                }
            ]
        }
    }
    cards = cards_from_sections(sections)
    hours = [card for card in cards if card.item_id.startswith("hours:") or card.source_family == "hours"]
    source = hours[0] if hours else cards[0]
    bundle = expand_hits([LexicalHit(card=source, score=1.0)], sections)
    text = " ".join(item.text for item in bundle.items)
    assert "09:00" in text or "monday" in text.lower()


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


@pytest.mark.asyncio
async def test_hybrid_uses_stored_index_without_document_embeds(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.customer_ai.providers.spaces import ENTITY_DOCUMENT
    from services.customer_ai.search.store import reset_memory_store, write_documents

    reset_memory_store()
    calls: list[str] = []

    async def fake_embed(space, texts):
        calls.append(space.input_mode)
        assert space.input_mode == "query"
        assert len(texts) == 1
        return VoyageVectors(space.space_id, [[1.0, 0.0]])

    monkeypatch.setattr("services.customer_ai.retrieve.hybrid.embed_texts", fake_embed)
    write_documents(
        None,
        [
            {
                "id": "services:hair",
                "tenant_id": "shop",
                "space_id": ENTITY_DOCUMENT.space_id,
                "source_family": "services",
                "source_id": "hair",
                "title": "Hair Removal",
                "search_text": "Hair Removal",
                "visible": True,
            }
        ],
        [[1.0, 0.0]],
    )
    sections = {"prices": {"catalog": [{"id": "hair", "labels": {"en": "Hair Removal"}, "active": True}]}}
    hits = await search_hybrid(
        cards_from_sections(sections),
        "hair removal",
        families={"services"},
        tenant_id="shop",
    )
    assert hits[0].card.item_id == "services:hair"
    assert calls == ["query"]


def test_product_expand_hydrates_from_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.customer_ai.retrieve.cards import TitleCard
    from services.customer_ai.retrieve.expand import expand_hits
    from services.customer_ai.retrieve.lexical import LexicalHit

    row = SimpleNamespace(
        id="serum-1",
        name="Vitamin C Serum",
        availability="in_stock",
        description="brightening",
        note="",
        price="25 USD",
        updated_at="2026-03-01T00:00:00+00:00",
    )
    monkeypatch.setattr(
        "services.customer_ai.retrieve.products.load_product_evidence",
        lambda tenant_id, product_id: evidence_from_product(row) if product_id == "serum-1" else None,
    )
    card = TitleCard(
        item_id="products:serum-1",
        source_family="products",
        title="Vitamin C Serum",
        search_text="vitamin c serum",
        revision="2026-03-01T00:00:00+00:00",
    )
    bundle = expand_hits([LexicalHit(card=card, score=1.0)], {}, tenant_id="shop")
    assert bundle.outcome == "found"
    assert bundle.items[0].source_id == "serum-1"
    assert "25 USD" in bundle.items[0].text


def test_archived_knowledge_is_not_carded() -> None:
    sections = {
        "knowledge": {
            "items": [
                {"id": "live", "title": "Live Policy", "body": "visible", "status": "active"},
                {"id": "gone", "title": "Archived Policy", "body": "hidden", "status": "archived"},
            ]
        }
    }
    cards = cards_from_sections(sections)
    assert [card.item_id for card in cards] == ["knowledge:live"]


@pytest.mark.asyncio
async def test_hybrid_prefers_pg_session_when_available(monkeypatch: pytest.MonkeyPatch) -> None:
    from contextlib import contextmanager

    from services.customer_ai.search.store import StoreHit, StoreQueryResult

    sessions: list[object] = []

    @contextmanager
    def _session(*, require=False):
        marker = object()
        sessions.append(marker)
        yield marker

    async def fake_embed(space, texts):
        return VoyageVectors(space.space_id, [[1.0, 0.0]])

    def fake_query(session, **kwargs):
        assert session is sessions[0]
        return StoreQueryResult(
            outcome="found",
            items=[
                StoreHit(
                    doc_id="services:hair",
                    tenant_id="shop",
                    source_family="services",
                    source_id="hair",
                    title="Hair",
                    search_text="Hair",
                    score=0.9,
                )
            ],
        )

    monkeypatch.setattr("services.customer_ai.retrieve.hybrid.embed_texts", fake_embed)
    monkeypatch.setattr("db.session.whatsapp_session", _session)
    monkeypatch.setattr("services.customer_ai.search.store.query_similar", fake_query)
    sections = {"prices": {"catalog": [{"id": "hair", "labels": {"en": "Hair Removal"}, "active": True}]}}
    hits = await search_hybrid(
        cards_from_sections(sections),
        "hair",
        families={"services"},
        tenant_id="shop",
    )
    assert sessions
    assert hits[0].card.item_id == "services:hair"
