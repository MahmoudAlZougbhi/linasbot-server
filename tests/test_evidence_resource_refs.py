"""Retrieved CM cards keep structured resource_ref lines in EVIDENCE."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from services.ai_setup.resource_attachment import customer_resource_descriptors
from services.ai_setup.setup_resources import resolve_published_resource
from services.brain.actions.resources import resolve_authorized_resource
from services.brain.compose.blocks import compose_evidence_context
from services.brain.contracts.plan import PlannerPlan, PlannerTask, TaskSpan
from services.brain.retrieve.cards import TitleCard
from services.brain.retrieve.hydrate import expand_hits
from services.brain.retrieve.lexical import LexicalHit
from services.brain.retrieve.products import evidence_from_product

_ATTACHMENTS = [
    {"id": "img-a", "kind": "image", "title": "Before", "status": "active", "sort_order": 0},
    {"id": "img-b", "kind": "image", "title": "After", "status": "active", "sort_order": 1},
    {
        "id": "lnk-book",
        "kind": "link",
        "title": "Book",
        "url": "https://example.com/book",
        "status": "active",
        "sort_order": 2,
    },
]


def _sections(family: str) -> dict:
    return {
        family: {
            "items": [
                {
                    "id": "cream-card",
                    "title": "Hydrating cream",
                    "body": "Published article body " + ("detail " * 80),
                    "attachments": list(_ATTACHMENTS),
                }
            ]
        }
    }


def _plan() -> PlannerPlan:
    return PlannerPlan(
        tasks=[
            PlannerTask(
                id="t_info",
                type="information",
                span=TaskSpan(text="cream", end=5),
                source_families=["knowledge", "care"],
            )
        ]
    )


def _assert_refs(text: str) -> None:
    assert "resource_ref=img-a" in text
    assert "resource_ref=img-b" in text
    assert "resource_ref=lnk-book" in text
    assert "kind=image" in text
    assert "kind=link" in text
    assert "summary images=2" in text
    assert "links=1" in text


def test_knowledge_chunk_keeps_resource_refs_in_evidence() -> None:
    card = TitleCard(
        item_id="knowledge:cream-card",
        source_family="knowledge",
        title="Hydrating cream",
        search_text="hydrating cream",
        body="short winning chunk",
    )
    bundle = expand_hits([LexicalHit(card=card, score=1.0)], _sections("knowledge"), tenant_id="shop")
    assert bundle.items
    text = bundle.items[0].text
    assert "short winning chunk" in text
    _assert_refs(text)
    ctx = compose_evidence_context(identity=None, plan=_plan(), bundle=bundle)
    _assert_refs(ctx)
    refs = {
        row["resource_ref"]
        for row in customer_resource_descriptors(_ATTACHMENTS, source_item_id="knowledge:cream-card")
    }
    assert refs == {"img-a", "img-b", "lnk-book"}
    extra_refs = bundle.items[0].extra.get("resource_refs") or []
    assert set(extra_refs) == refs


def test_care_card_keeps_resource_refs_in_evidence() -> None:
    card = TitleCard(
        item_id="care:cream-card",
        source_family="care",
        title="Aftercare cream",
        search_text="aftercare cream",
        body="care chunk",
    )
    bundle = expand_hits([LexicalHit(card=card, score=1.0)], _sections("care"), tenant_id="shop")
    assert bundle.items
    _assert_refs(bundle.items[0].text)
    ctx = compose_evidence_context(identity=None, plan=_plan(), bundle=bundle)
    _assert_refs(ctx)


def test_descriptor_ids_are_usable_by_check_and_send(monkeypatch: pytest.MonkeyPatch) -> None:
    pointer = SimpleNamespace(content_version_id="rev-1")
    monkeypatch.setattr(
        "services.ai_setup.setup_resources.load_published_content",
        lambda _tenant: (pointer, _sections("knowledge")),
    )
    found = resolve_published_resource(tenant_id="shop", resource_ref="img-a")
    assert found["ok"] is True
    assert found["resource"]["resource_type"] == "image"
    sent = resolve_authorized_resource(tenant_id="shop", resource_ref="lnk-book")
    assert sent["ok"] is True
    assert sent["resource"]["resource_type"] == "link"


def test_product_evidence_keeps_image_and_link_refs() -> None:
    row = SimpleNamespace(
        id="p1",
        name="Hydrating cream",
        description="jar",
        note="",
        image_url="",
        product_url="",
        video_url="",
        price="12",
        availability="in_stock",
        updated_at="",
        images=[
            SimpleNamespace(media_id="img-a", id="", filename="before.jpg", sort_order=0),
            SimpleNamespace(media_id="img-b", id="", filename="after.jpg", sort_order=1),
        ],
        links=[SimpleNamespace(id="lnk-book", url="https://example.com/book", label="Book")],
    )
    item = evidence_from_product(row)
    assert item is not None
    _assert_refs(item.text)
    assert set(item.extra.get("resource_refs") or []) == {"img-a", "img-b", "lnk-book"}
