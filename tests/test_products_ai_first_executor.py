"""Products AI-first executor: Terra decides; system search/fetch/send only."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from services.brain.contracts.actions import ActionProposal
from services.brain.contracts.evidence import EvidenceBundle
from services.brain.contracts.turn import CustomerTurn
from services.brain.retrieve.products import evidence_from_product
from services.brain.tools.registry import execute_tool
from services.products.authorized_media import source_allowed

_P1 = SimpleNamespace(
    id="p1",
    name="Hydrating cream",
    description="jar " + ("detail " * 40),
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


def _product_record(ref: str = "img-a", product_id: str = "p1", kind: str = "image") -> dict[str, Any]:
    return {
        "resource_ref": ref,
        "tenant_id": "shop",
        "source_type": "product_media",
        "source_item_id": f"products:{product_id}",
        "product_id": product_id,
        "resource_type": kind,
        "title": "Hydrating cream",
        "media_id": ref if kind != "link" else "",
        "external_url": "https://example.com/book" if kind == "link" else "",
    }


def _patch_product_resolve(monkeypatch: pytest.MonkeyPatch, records: dict[str, dict[str, Any]]) -> None:
    def _resolve(**kwargs: Any) -> dict[str, Any] | None:
        ref = str(kwargs.get("resource_ref") or "")
        row = records.get(ref)
        if row is None:
            return None
        allowed = kwargs.get("allowed_source_ids")
        if not source_allowed(str(row.get("product_id") or ""), allowed if isinstance(allowed, list) else None):
            return None
        return dict(row)

    monkeypatch.setattr("services.products.authorized_media.resolve_customer_product_resource", _resolve)
    monkeypatch.setattr(
        "services.brain.actions.resources.resolve_published_resource",
        lambda **_k: {"ok": False, "error": "resource_not_found"},
    )


@pytest.mark.asyncio
async def test_search_products_keeps_attachment_refs(monkeypatch: pytest.MonkeyPatch) -> None:
    item = evidence_from_product(_P1)
    assert item is not None

    async def _retrieve(_ctx: object) -> EvidenceBundle:
        return EvidenceBundle(items=[item], outcome="found")

    monkeypatch.setattr("services.brain.retrieve.orchestrate.retrieve_published", _retrieve)
    result = await execute_tool("search_products", {"query": "cream"}, CustomerTurn(tenant_id="shop"))
    assert result["ok"] is True
    row = result["data"][0]
    assert "resource_ref=img-a" in row["text"]
    assert "resource_ref=img-b" in row["text"]
    assert set(row["resource_refs"]) == {"img-a", "img-b", "lnk-book"}


@pytest.mark.asyncio
async def test_get_product_exposes_resource_refs(monkeypatch: pytest.MonkeyPatch) -> None:
    item = evidence_from_product(_P1)
    monkeypatch.setattr("services.brain.retrieve.products.load_product_evidence", lambda *_a, **_k: item)
    result = await execute_tool("get_product", {"id": "p1"}, CustomerTurn(tenant_id="shop"))
    assert result["ok"] is True
    assert result["data"]["resource_refs"] == ["img-a", "img-b", "lnk-book"]
    assert "kind=image" in result["data"]["text"]


@pytest.mark.asyncio
async def test_check_product_inventory_does_not_send(monkeypatch: pytest.MonkeyPatch) -> None:
    sends: list[str] = []
    monkeypatch.setattr(
        "services.products.authorized_media.list_product_inventory_items",
        lambda **_k: [
            {"id": "img-a", "kind": "image", "title": "Before", "source_item_id": "products:p1"},
            {"id": "img-b", "kind": "image", "title": "After", "source_item_id": "products:p1"},
            {"id": "lnk-book", "kind": "link", "title": "Book", "source_item_id": "products:p1"},
        ],
    )
    monkeypatch.setattr("services.brain.tools.resource_inventory.index_published_resources", lambda _tid: {})
    monkeypatch.setattr(
        "services.brain.reply.setup_resource_outbound.send_pending_setup_resources",
        lambda **_k: sends.append("send") or {"ok": True, "sent": []},
    )
    turn = CustomerTurn(tenant_id="shop")
    result = await execute_tool("check_setup_resources", {"product_id": "p1"}, turn)
    assert result["ok"] is True
    assert result["data"]["images"] == 2
    assert result["data"]["links"] == 1
    assert {row["id"] for row in result["data"]["items"]} == {"img-a", "img-b", "lnk-book"}
    assert sends == []
    assert turn.extra.get("resource_delivery") is None


@pytest.mark.asyncio
async def test_send_chosen_product_image_queues_channel(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_product_resolve(monkeypatch, {"img-a": _product_record()})
    turn = CustomerTurn(tenant_id="shop", extra={"evidence_source_ids": ["products:p1"]})
    result = await execute_tool("send_resource", {"resource_id": "img-a", "kind": "image"}, turn)
    assert result["ok"] is True
    delivery = turn.extra.get("resource_delivery") or {}
    assert delivery.get("ok") is True
    assert [row["id"] for row in delivery.get("sent") or []] == ["img-a"]
    user_data: dict[str, Any] = {"tenant_id": "shop"}
    from services.brain.reply.product_media_outbound import send_pending_product_media
    from services.brain.tools.resource_delivery import queue_channel_delivery

    queue_channel_delivery(user_data, delivery)
    captured: list[str] = []

    async def capture(to, text, image, audio):
        captured.append(str(image or text or ""))

    outbound = await send_pending_product_media(
        user_data=user_data,
        sender_id="psid-1",
        adapter=None,
        inbound_event_id=None,
        channel="instagram_dm",
        binding_id="b1",
        capture_send=capture,
        capture_to="ig:1",
    )
    assert outbound.get("delivery_result") == "simulated"
    assert any("product-media:img-a" in item for item in captured)


def test_send_rejects_cross_product_media(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.brain.actions.resources import send_resource

    _patch_product_resolve(monkeypatch, {"img-b": _product_record("img-b", product_id="p2")})
    receipt = send_resource(
        tenant_id="shop",
        proposal=ActionProposal(
            task_id="t1",
            action_type="send_resource",
            target_id="img-b",
            fields={"kind": "image", "allowed_source_ids": ["products:p1"]},
        ),
    )
    assert receipt.state == "rejected"
    assert receipt.reason == "resource_not_found"


def test_send_rejects_product_kind_swap(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.brain.actions.resources import send_resource

    _patch_product_resolve(monkeypatch, {"img-a": _product_record()})
    receipt = send_resource(
        tenant_id="shop",
        proposal=ActionProposal(
            task_id="t1",
            action_type="send_resource",
            target_id="img-a",
            fields={"kind": "video"},
        ),
    )
    assert receipt.state == "rejected"
    assert receipt.reason == "kind_mismatch"


def test_empty_product_inventory_is_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("services.products.authorized_media.list_product_inventory_items", lambda **_k: [])
    monkeypatch.setattr("services.brain.tools.resource_inventory.index_published_resources", lambda _tid: {})
    from services.brain.tools.resource_inventory import list_published_inventory

    inventory = list_published_inventory(tenant_id="shop", product_ids=["p1"])
    assert inventory["images"] == 0
    assert inventory["items"] == []
