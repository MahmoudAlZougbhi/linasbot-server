"""Zero-to-query auto-index E2E for a throwaway tenant (publish → ACTIVE → edit → delete)."""

from __future__ import annotations

import uuid
from typing import Any

from services.cm.storage import get_draft, put_draft
from services.customer_ai.retrieve.cards import load_published_cards
from services.customer_ai.search.index_lifecycle import get_lifecycle
from services.customer_ai.search.store import reset_memory_store


def _put(section: str, tenant_id: str, payload: dict[str, Any]) -> None:
    env = get_draft(section, tenant_id=tenant_id, create_default=True)
    merged = {**dict(env.payload), **payload}
    put_draft(section, payload=merged, if_match=env.etag, tenant_id=tenant_id, updated_by="auto-index-e2e")


def seed_minimal_setup(tenant_id: str, *, price: str = "80 USD", faq: bool = True) -> None:
    amount = float(price.split()[0])
    _put(
        "prices",
        tenant_id,
        {
            "catalog": [
                {
                    "id": "glow_serum",
                    "item_type": "product",
                    "labels": {"en": "Glow Serum", "ar": "سيروم التوهج", "fr": "Sérum éclat"},
                    "description": f"Glow Serum {price}",
                    "active": True,
                    "base_price": amount,
                    "currency": "USD",
                }
            ],
            "price_entries": [
                {
                    "id": "glow_serum_usd",
                    "catalog_item_id": "glow_serum",
                    "amount": amount,
                    "currency": "USD",
                }
            ],
        },
    )
    _put(
        "branches",
        tenant_id,
        {
            "items": [
                {
                    "id": "main",
                    "labels": {"en": "Main Branch"},
                    "address": "Main street 1",
                    "ai_search_description": "main branch hours",
                }
            ]
        },
    )
    _put(
        "opening_hours",
        tenant_id,
        {
            "items": [
                {
                    "id": "main_hours",
                    "title": "Main hours",
                    "monday": {"open": "09:00", "close": "18:00", "closed": False},
                    "ai_search_description": "monday hours 9 to 6",
                }
            ]
        },
    )
    faq_items = []
    if faq:
        faq_items.append(
            {
                "qa_group_id": "faq_parking",
                "status": "active",
                "variants": [
                    {
                        "language": "en",
                        "question": "Is parking available?",
                        "answer": "Yes, free parking at Main Branch.",
                    }
                ],
                "ai_search_title": "parking",
                "ai_search_description": "parking available free",
            }
        )
    _put("faq", tenant_id, {"items": faq_items})
    _put(
        "knowledge",
        tenant_id,
        {
            "items": [
                {
                    "id": "aftercare",
                    "title": "Aftercare",
                    "body": "Do not wash the treated area for 24 hours.",
                    "status": "active",
                    "ai_search_description": "aftercare wash",
                }
            ]
        },
    )


async def run_new_tenant_auto_index_e2e(*, tenant_id: str = "") -> dict[str, Any]:
    from services.cm.publish import publish_draft
    from services.customer_ai.search.index_schedule import run_tenant_index_job

    tid = (tenant_id or "").strip() or f"auto-idx-{uuid.uuid4().hex[:10]}"
    reset_memory_store()
    seed_minimal_setup(tid, price="80 USD", faq=True)
    first = await publish_draft(tenant_id=tid, published_by="auto-index-e2e")
    first_index = first.brain_index_status or {}
    if not first_index.get("ready"):
        first_index = await run_tenant_index_job(tid, revision=first.content_version_id, reason="e2e-first")
    life = get_lifecycle(tid)
    cards = load_published_cards(tid)
    titles = {card.title.lower() for card in cards}
    ids = {card.item_id.split(":", 1)[-1] for card in cards}
    first_ok = (
        str(life.get("status") or "") == "ACTIVE"
        and "glow serum" in titles
        and "faq_parking" in ids
        and bool(first_index.get("ready"))
    )

    seed_minimal_setup(tid, price="95 USD", faq=True)
    second = await publish_draft(tenant_id=tid, published_by="auto-index-e2e")
    second_index = second.brain_index_status or {}
    if not second_index.get("ready"):
        second_index = await run_tenant_index_job(tid, revision=second.content_version_id, reason="e2e-edit")
    cards2 = load_published_cards(tid)
    price_text = " ".join(card.search_text for card in cards2)
    life2 = get_lifecycle(tid)
    edit_ok = (
        second.content_version_id != first.content_version_id
        and str(life2.get("status") or "") == "ACTIVE"
        and "95" in price_text
        and "80 USD" not in price_text
        and str(life2.get("rollback_version") or "") == first.content_version_id
        and bool(second_index.get("ready"))
    )

    seed_minimal_setup(tid, price="95 USD", faq=False)
    third = await publish_draft(tenant_id=tid, published_by="auto-index-e2e")
    third_index = third.brain_index_status or {}
    if not third_index.get("ready"):
        third_index = await run_tenant_index_job(tid, revision=third.content_version_id, reason="e2e-delete")
    cards3 = load_published_cards(tid)
    ids3 = {card.item_id.split(":", 1)[-1] for card in cards3}
    life3 = get_lifecycle(tid)
    delete_ok = "faq_parking" not in ids3 and str(life3.get("status") or "") == "ACTIVE" and bool(third_index.get("ready"))

    return {
        "ok": first_ok and edit_ok and delete_ok,
        "tenant_id": tid,
        "first_active": first_ok,
        "edit_new_active": edit_ok,
        "faq_removed": delete_ok,
        "first_version": first.content_version_id,
        "second_version": second.content_version_id,
        "third_version": third.content_version_id,
        "lifecycle": {
            "status": life3.get("status"),
            "active_version": life3.get("active_version"),
            "rollback_version": life3.get("rollback_version"),
        },
        "manual_index_required": False,
    }
