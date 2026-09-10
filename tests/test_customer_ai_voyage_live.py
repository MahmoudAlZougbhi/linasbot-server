"""Authorized live Voyage checks. Skip when VOYAGE_API_KEY is absent."""

from __future__ import annotations

import pytest

from services.customer_ai.flags import voyage_api_key
from services.customer_ai.providers.spaces import (
    ENTITY_DOCUMENT,
    ENTITY_QUERY,
    KNOWLEDGE_DOCUMENT,
    RERANK_MODEL,
    compatible,
)
from services.customer_ai.providers.voyage_client import (
    VoyageContractError,
    embed_contextual_groups,
    embed_texts,
    rerank_texts,
)
from services.customer_ai.retrieve.cards import cards_from_sections
from services.customer_ai.retrieve.hybrid import search_hybrid


def _require_key() -> None:
    if not voyage_api_key():
        pytest.skip("VOYAGE_API_KEY not configured")


@pytest.mark.asyncio
async def test_live_entity_embed_dims_and_franco_query() -> None:
    _require_key()
    docs = await embed_texts(
        ENTITY_DOCUMENT,
        ["Laser hair removal service", "Botox injection service"],
    )
    query = await embed_texts(ENTITY_QUERY, ["بدي شيل شعر الإيدين"])
    assert compatible(ENTITY_DOCUMENT, ENTITY_QUERY)
    assert len(docs.vectors) == 2
    assert len(docs.vectors[0]) == 1024
    assert len(query.vectors[0]) == 1024
    hair = sum(a * b for a, b in zip(query.vectors[0], docs.vectors[0], strict=True))
    botox = sum(a * b for a, b in zip(query.vectors[0], docs.vectors[1], strict=True))
    assert hair > botox


@pytest.mark.asyncio
async def test_live_contextual_knowledge_groups() -> None:
    _require_key()
    groups = await embed_contextual_groups(
        KNOWLEDGE_DOCUMENT,
        [
            [
                "Aftercare booklet",
                "Do not wash the treated area for 24 hours after laser.",
            ]
        ],
    )
    assert len(groups) == 1
    assert len(groups[0].vectors) == 2
    assert len(groups[0].vectors[0]) == 1024
    assert groups[0].space_id == KNOWLEDGE_DOCUMENT.space_id


@pytest.mark.asyncio
async def test_live_rerank_25_orders_relevant_first() -> None:
    _require_key()
    hits = await rerank_texts(
        query="hair removal price",
        documents=["Laser hair removal 80 USD", "Opening hours Monday to Saturday", "Botox filler notes"],
        model=RERANK_MODEL,
        top_k=3,
    )
    assert hits
    assert hits[0].index == 0
    assert hits[0].score > hits[-1].score


@pytest.mark.asyncio
async def test_live_hybrid_picks_catalog_service() -> None:
    _require_key()
    sections = {
        "prices": {
            "catalog": [
                {
                    "id": "hair",
                    "labels": {"en": "Hair Removal"},
                    "aliases": ["lazer", "إزالة الشعر"],
                    "description": "laser hair removal",
                    "active": True,
                },
                {
                    "id": "botox",
                    "labels": {"en": "Botox"},
                    "description": "wrinkle injection",
                    "active": True,
                },
            ]
        }
    }
    try:
        hits = await search_hybrid(cards_from_sections(sections), "بدي hair removal", families={"services"}, limit=3)
    except VoyageContractError as exc:
        if "429" in str(exc):
            pytest.skip("Voyage rate-limited after earlier live calls")
        raise
    assert hits
    assert hits[0].card.item_id == "services:hair"
