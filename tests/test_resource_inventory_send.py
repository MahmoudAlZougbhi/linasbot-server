"""AI-orchestrated resource check vs send — no silent kind fallback, no outbound on check."""

from __future__ import annotations

from typing import Any

import pytest

from services.brain.contracts.actions import ActionProposal
from services.brain.contracts.evidence import EvidenceBundle, EvidenceItem
from services.brain.contracts.reply import FinalReplyEnvelope, OutboundMessage, TurnResult
from services.brain.contracts.turn import CustomerTurn
from services.brain.tools.registry import execute_tool
from tests.plan_builders import explicit_plan

_INDEX = {
    "img-1": {
        "resource_ref": "img-1",
        "title": "Before photo",
        "description": "face before",
        "resource_type": "image",
        "source_item_id": "knowledge:laser",
        "tenant_id": "shop",
    },
    "vid-1": {
        "resource_ref": "vid-1",
        "title": "After video",
        "description": "treatment video",
        "resource_type": "video",
        "source_item_id": "knowledge:laser",
        "tenant_id": "shop",
    },
    "lnk-1": {
        "resource_ref": "lnk-1",
        "title": "Booking link",
        "description": "book now",
        "resource_type": "link",
        "source_item_id": "knowledge:laser",
        "tenant_id": "shop",
        "external_url": "https://book.example/laser",
    },
}


def _patch_index(monkeypatch: pytest.MonkeyPatch, index: dict[str, dict[str, Any]] | None = None) -> None:
    payload = dict(index if index is not None else _INDEX)

    def _resolve(**kwargs: Any) -> dict[str, Any]:
        ref = str(kwargs.get("resource_ref") or "")
        row = payload.get(ref)
        if row is None:
            return {"ok": False, "error": "resource_not_found"}
        return {"ok": True, "resource": dict(row)}

    monkeypatch.setattr("services.ai_setup.setup_resources.index_published_resources", lambda _tid: payload)
    monkeypatch.setattr("services.brain.tools.resource_inventory.index_published_resources", lambda _tid: payload)
    monkeypatch.setattr("services.brain.actions.resources.resolve_published_resource", _resolve)
    monkeypatch.setattr("services.brain.tools.resource_delivery.resolve_authorized_resource", _resolve)
    monkeypatch.setattr(
        "services.brain.actions.resources.resolve_authorized_resource",
        lambda **kwargs: (
            _resolve(**kwargs)
            if payload.get(str(kwargs.get("resource_ref") or ""))
            else {"ok": False, "error": "resource_not_found"}
        ),
    )


@pytest.mark.asyncio
async def test_check_inventory_has_no_outbound(monkeypatch: pytest.MonkeyPatch) -> None:
    sends: list[Any] = []
    monkeypatch.setattr(
        "services.brain.reply.setup_resource_outbound.send_pending_setup_resources",
        lambda **_k: sends.append("send") or {"ok": True, "sent": []},
    )
    _patch_index(monkeypatch, {k: v for k, v in _INDEX.items() if k != "img-1"})
    turn = CustomerTurn(tenant_id="shop", conversation_id="c1", extra={"evidence_source_ids": ["knowledge:laser"]})
    result = await execute_tool("check_setup_resources", {"query": "photos"}, turn)
    assert result["ok"] is True
    data = result["data"]
    assert data["images"] == 0
    assert data["videos"] == 1
    assert data["links"] == 1
    assert {row["kind"] for row in data["items"]} == {"video", "link"}
    assert sends == []
    assert turn.extra.get("resource_delivery") is None
    assert turn.state.resource_inventory["videos"] == 1


@pytest.mark.asyncio
async def test_send_resource_video_only_after_choice(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_index(monkeypatch)
    turn = CustomerTurn(tenant_id="shop", conversation_id="c1")
    result = await execute_tool("send_resource", {"resource_id": "vid-1", "kind": "video"}, turn)
    assert result["ok"] is True
    delivery = turn.extra.get("resource_delivery") or {}
    assert delivery.get("ok") is True
    assert [row["kind"] for row in delivery.get("sent") or []] == ["video"]
    assert [row["id"] for row in delivery.get("sent") or []] == ["vid-1"]
    assert result["data"]["reason"] != "awaiting_delivery"


@pytest.mark.asyncio
async def test_check_all_zero_does_not_send(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_index(monkeypatch, {})
    turn = CustomerTurn(tenant_id="shop", extra={"evidence_source_ids": ["knowledge:missing"]})
    result = await execute_tool("check_setup_resources", {"query": "photos"}, turn)
    assert result["data"]["images"] == 0
    assert result["data"]["videos"] == 0
    assert result["data"]["links"] == 0
    assert result["data"]["items"] == []
    assert turn.extra.get("resource_delivery") is None


def test_send_resource_rejects_kind_swap(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.brain.actions.resources import send_resource

    _patch_index(monkeypatch)
    receipt = send_resource(
        tenant_id="shop",
        proposal=ActionProposal(task_id="t1", action_type="send_resource", target_id="vid-1", fields={"kind": "image"}),
    )
    assert receipt.state == "rejected"
    assert receipt.reason == "kind_mismatch"


@pytest.mark.asyncio
async def test_resource_request_checks_does_not_auto_send(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.brain.turn_pipeline import run_dm_after_gates

    plan = explicit_plan("send me photos please", ("resource_request", ["knowledge"]))

    def fake_plan(_message: str):
        return plan

    async def fake_retrieve(_ctx):
        return EvidenceBundle(
            outcome="found",
            items=[
                EvidenceItem(
                    evidence_id="knowledge:laser",
                    source_family="knowledge",
                    source_id="laser",
                    title="Laser",
                    text="Laser treatment",
                )
            ],
        )

    async def fake_generate(*_a, **kwargs):
        extra = dict(kwargs.get("extra") or {})
        return TurnResult(
            stop_reason="ok",
            envelope=FinalReplyEnvelope(
                decision="reply",
                messages=[OutboundMessage(destination="dm", text="في فيديو ورابط، ما في صور — شو بتفضّل؟")],
            ),
            extra={**extra, "phase": "generate"},
        )

    async def _no_confirm(*_a, **_k):
        return None

    _patch_index(monkeypatch, {k: v for k, v in _INDEX.items() if k != "img-1"})
    monkeypatch.setattr("services.brain.agent.loop.default_agentic_plan", fake_plan)

    async def _no_terra(*_a, **_k):
        return [], [], 0, {}

    monkeypatch.setattr("services.brain.agent.loop.run_terra_request_round", _no_terra)
    monkeypatch.setattr("services.brain.agent.multi_retrieve.retrieve_published", fake_retrieve)
    monkeypatch.setattr("services.brain.agent.loop.generate_verified", fake_generate)
    monkeypatch.setattr("services.brain.agent.loop.reserve_generative", lambda *_a, **_k: None)
    monkeypatch.setattr("services.brain.turn_pipeline.try_confirm_pending", _no_confirm)
    monkeypatch.setattr("services.brain.turn_pipeline._exact_faq_result", lambda *_a, **_k: None)

    async def _no_sem(*_a, **_k):
        return None

    monkeypatch.setattr("services.brain.turn_pipeline._semantic_faq_result", _no_sem)
    turn = CustomerTurn(tenant_id="shop", conversation_id="c1", event_ids=["m1"], channel="instagram_dm")
    result = await run_dm_after_gates(turn, message="send me photos please", channel="instagram_dm")
    tools = [row.get("tool") for row in (result.extra.get("tool_calls") or [])]
    assert "check_setup_resources" in tools
    assert not any(item.get("action_type") == "send_resource" for item in result.extra.get("receipts") or [])
    assert (result.extra.get("resource_delivery") or {}).get("items") in (None, [])
    assert result.extra.get("awaiting_confirmation") is not True
    assert "فيديو" in (result.envelope.reply_text or "")


@pytest.mark.asyncio
async def test_send_resource_invokes_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.brain.reply.setup_resource_outbound import send_pending_setup_resources

    called: list[str] = []

    async def fake_attach(*_a, **_k):
        called.append("adapter")
        return {"success": True, "message_id": "mid-1"}

    monkeypatch.setattr("services.integrations.meta.meta_attachment_send.send_stored_meta_attachment", fake_attach)
    monkeypatch.setattr(
        "services.brain.reply.setup_resource_outbound.resolve_published_resource",
        lambda **_k: {
            "ok": True,
            "resource": {
                "resource_ref": "img-1",
                "tenant_id": "shop",
                "resource_type": "image",
                "storage_key": "img-1",
                "mime_type": "image/jpeg",
            },
        },
    )
    monkeypatch.setattr(
        "services.brain.reply.setup_resource_outbound.load_media_meta",
        lambda **_k: {"tenant_id": "shop", "mime": "image/jpeg", "filename": "before.jpg"},
    )
    monkeypatch.setattr("services.brain.reply.setup_resource_outbound.load_media_bytes", lambda **_k: b"jpeg-bytes")

    class _Adapter:
        async def send_text_message(self, *_a, **_k):
            raise AssertionError("image send must not fall back to text")

    result = await send_pending_setup_resources(
        user_data={
            "tenant_id": "shop",
            "_pending_setup_resources": {
                "ok": True,
                "items": [{"resource_ref": "img-1", "resource_type": "image", "title": "Before"}],
            },
        },
        sender_id="psid-1",
        adapter=_Adapter(),
        inbound_event_id=None,
        channel="instagram_dm",
        binding_id="bind-1",
    )
    assert called == ["adapter"]
    assert result.get("claimed_sent") is True
    assert result.get("delivery_result") == "channel_sent"


@pytest.mark.asyncio
async def test_empty_text_still_sends_queued_resource() -> None:
    from services.integrations.meta.meta_social_text_send import send_meta_social_outbound

    captured: list[str] = []

    async def capture(to, text, image, audio):
        captured.append(str(image or text or ""))

    result = await send_meta_social_outbound(
        namespaced_id="ig:1",
        message_text="",
        image_url=None,
        audio_url=None,
        capture_send=capture,
        adapter=None,
        inbound_event_id=None,
        channel="instagram_dm",
        binding_id="b1",
        sender_id="psid-1",
        user_data={
            "tenant_id": "shop",
            "_pending_setup_resources": {
                "ok": True,
                "items": [{"resource_ref": "vid-1", "resource_type": "video", "title": "After"}],
            },
        },
    )
    assert result.get("success") is True
    assert any("setup-resource:vid-1" in item for item in captured)
