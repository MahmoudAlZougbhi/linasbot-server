"""Optimistic Live Chat send: durable enqueue, no Graph wait, pause-once, status events."""

from __future__ import annotations

import time
from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.live_chat_operator_delivery_status import compose_operator_text_result
from services.live_chat_operator_queue import live_chat_durable_mode, queue_unavailable_result
from services.live_chat_service import live_chat_service
from services.requests.manual_mode import activate_manual_mode


def _send_patches(*extra: object, user_id: str = "instagram:178414:psid"):
    pause_result = MagicMock(activated=True, already_active=False, control_epoch=3)
    return (
        patch(
            "services.live_chat_service_operator._try_acquire_operator_send_idempotency",
            new_callable=AsyncMock,
            return_value=(True, None),
        ),
        patch("services.live_chat_service_operator._release_operator_idempotency_lock", new_callable=AsyncMock),
        patch("utils.utils.get_canonical_user_id_and_phone", return_value=(user_id, None)),
        patch("utils.utils.get_firestore_db", return_value=None),
        patch("utils.utils.save_conversation_message_to_firestore", new_callable=AsyncMock),
        patch(
            "services.requests.manual_mode.activate_manual_mode",
            new_callable=AsyncMock,
            return_value=pause_result,
        ),
        patch.object(live_chat_service, "_refresh_index_for_conversation", new_callable=AsyncMock),
        patch("services.live_chat_operator_delivery_status.publish_operator_delivery_status", new_callable=AsyncMock),
        patch("services.live_chat_operator_delivery_status.persist_operator_delivery_status", new_callable=AsyncMock),
        *extra,
    )


def test_durable_mode_sync_when_redis_not_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("services.queues.config.redis_required", lambda: False)
    assert live_chat_durable_mode() == "sync"


def test_durable_mode_unavailable_when_required_but_not_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("services.queues.config.redis_required", lambda: True)
    monkeypatch.setattr("services.omnichannel.enqueue.queue_is_durable", lambda: False)
    assert live_chat_durable_mode() == "unavailable"
    result = queue_unavailable_result(channel="instagram")
    assert result["success"] is False
    assert result["error"] == "queue_unavailable"
    assert result["delivery_status"] == "failed"


def test_compose_queued_is_not_delivered() -> None:
    payload = compose_operator_text_result(
        {"success": True, "queued": True, "delivered": False, "channel": "instagram"},
        {"status": "human"},
        client_message_id="local-1",
    )
    assert payload["success"] is True
    assert payload["delivered"] is False
    assert payload["queued"] is True
    assert payload["delivery_status"] == "sending"
    assert payload["client_message_id"] == "local-1"


@pytest.mark.asyncio
async def test_instagram_queued_send_does_not_wait_for_graph() -> None:
    enqueue = MagicMock(
        return_value={"success": True, "queued": True, "delivered": False, "delivery_status": "sending"}
    )
    slow = AsyncMock()

    async def hang(*_a, **_k):
        await __import__("asyncio").sleep(8)
        raise AssertionError("Graph must not run on the HTTP path")

    slow.side_effect = hang

    with ExitStack() as stack:
        for cm in _send_patches(
            patch("services.live_chat_operator_queue.live_chat_durable_mode", lambda: "enqueue"),
            patch("services.live_chat_operator_queue.enqueue_live_chat_operator_text", enqueue),
            patch("services.requests.delivery.deliver_meta_dm", slow),
        ):
            stack.enter_context(cm)
        started = time.monotonic()
        result = await live_chat_service.send_operator_message(
            conversation_id="c-ig-1",
            user_id="instagram:178414:psid",
            message="hello tester",
            operator_id="op1",
            adapter=MagicMock(),
            tenant_id="linas",
            idempotency_key="local-abc",
        )
        elapsed = time.monotonic() - started
    assert elapsed < 1.5
    assert result.get("success") is True
    assert result.get("queued") is True
    assert result.get("delivered") is False
    assert result.get("delivery_status") == "sending"
    enqueue.assert_called_once()
    slow.assert_not_awaited()


@pytest.mark.asyncio
async def test_instagram_queue_unavailable_fails_closed() -> None:
    slow = AsyncMock()
    with ExitStack() as stack:
        for cm in _send_patches(
            patch("services.live_chat_operator_queue.live_chat_durable_mode", lambda: "unavailable"),
            patch("services.requests.delivery.deliver_meta_dm", slow),
            patch(
                "services.requests.manual_mode.resume_manual_mode",
                new_callable=AsyncMock,
                return_value=MagicMock(control_epoch=4, already_active=False, audit_recorded=False),
            ),
        ):
            stack.enter_context(cm)
        result = await live_chat_service.send_operator_message(
            conversation_id="c-ig-1",
            user_id="instagram:178414:psid",
            message="hello tester",
            operator_id="op1",
            adapter=MagicMock(),
            tenant_id="linas",
            idempotency_key="local-abc",
        )
    assert result.get("success") is False
    assert "queue_unavailable" in str(result.get("error") or "")
    assert result.get("delivery_status") == "failed"
    slow.assert_not_awaited()


@pytest.mark.asyncio
async def test_second_manual_pause_skips_firestore(monkeypatch: pytest.MonkeyPatch) -> None:
    import config

    config.user_in_human_takeover_mode.clear()
    writes = {"n": 0}

    async def fake_set(*_a, **_k):
        writes["n"] += 1

    monkeypatch.setattr("utils.utils.set_human_takeover_status", fake_set)
    monkeypatch.setattr("utils.utils.get_canonical_user_id_and_phone", lambda uid, *a, **k: (uid, None))
    first = await activate_manual_mode(
        conversation_id="c-ig",
        user_id="instagram:1",
        actor_user_id="op-1",
    )
    second = await activate_manual_mode(
        conversation_id="c-ig",
        user_id="instagram:1",
        actor_user_id="op-1",
    )
    config.user_in_human_takeover_mode.clear()
    assert first.activated is True
    assert first.already_active is False
    assert second.already_active is True
    assert writes["n"] == 1


@pytest.mark.asyncio
async def test_message_status_notify_requires_live_chat_user(monkeypatch: pytest.MonkeyPatch) -> None:
    published: list[tuple[str, dict]] = []

    async def fake_broadcast(event_type: str, data: dict) -> None:
        published.append((event_type, data))

    monkeypatch.setattr(
        "modules.live_chat_api_helpers.broadcast_sse_event",
        fake_broadcast,
    )
    from services.live_chat_operator_delivery_status import notify_live_chat_operator_job

    await notify_live_chat_operator_job({"outbox_id": "x"}, delivery_status="sent")
    assert published == []
    await notify_live_chat_operator_job(
        {
            "live_chat_user_id": "+96170123456",
            "live_chat_conversation_id": "c1",
            "live_chat_client_message_id": "local-1",
            "tenant_id": "linas",
        },
        delivery_status="sent",
    )
    assert published[0][0] == "message_status"
    assert published[0][1]["delivery_status"] == "sent"
    assert published[0][1]["user_id"] == "+96170123456"


@pytest.mark.asyncio
async def test_whatsapp_sync_when_durable_off() -> None:
    adapter = MagicMock()
    adapter.send_text_message = AsyncMock(return_value={"success": True})
    with ExitStack() as stack:
        for cm in _send_patches(
            patch("services.live_chat_operator_queue.live_chat_durable_mode", lambda: "sync"),
            user_id="+96170123456",
        ):
            stack.enter_context(cm)
        result = await live_chat_service.send_operator_message(
            conversation_id="c-wa",
            user_id="+96170123456",
            message="hello",
            operator_id="op1",
            adapter=adapter,
            tenant_id="linas",
            idempotency_key="local-wa",
        )
    assert result.get("success") is True
    assert result.get("delivered") is True
    adapter.send_text_message.assert_awaited_once()


def test_whatsapp_enqueue_skipped_in_sync_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.live_chat_operator_queue import try_enqueue_live_chat_whatsapp

    monkeypatch.setattr("services.live_chat_operator_queue.live_chat_durable_mode", lambda: "sync")
    assert (
        try_enqueue_live_chat_whatsapp(
            tenant_id="linas",
            user_id="+96170123456",
            canonical_user_id="+96170123456",
            conversation_id="c1",
            text="hello",
        )
        is None
    )


def test_whatsapp_enqueue_fail_closed_without_waba(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.live_chat_operator_queue import try_enqueue_live_chat_whatsapp

    monkeypatch.setattr("services.live_chat_operator_queue.live_chat_durable_mode", lambda: "enqueue")
    monkeypatch.setattr("services.live_chat_operator_queue._active_whatsapp_connection_id", lambda _tenant: None)
    result = try_enqueue_live_chat_whatsapp(
        tenant_id="linas",
        user_id="+96170123456",
        canonical_user_id="+96170123456",
        conversation_id="c1",
        text="hello",
    )
    assert result is not None
    assert result["success"] is False
    assert result["error"] == "whatsapp_not_connected"
    assert result["delivery_status"] == "failed"


@pytest.mark.asyncio
async def test_whatsapp_redis_required_does_not_sync_adapter() -> None:
    adapter = MagicMock()
    adapter.send_text_message = AsyncMock(side_effect=AssertionError("adapter must not run when Redis required"))
    with ExitStack() as stack:
        for cm in _send_patches(
            patch("services.live_chat_operator_queue.live_chat_durable_mode", lambda: "enqueue"),
            patch("services.live_chat_operator_queue._active_whatsapp_connection_id", lambda _tenant: None),
            user_id="+96170123456",
        ):
            stack.enter_context(cm)
        result = await live_chat_service.send_operator_message(
            conversation_id="c-wa",
            user_id="+96170123456",
            message="hello",
            operator_id="op1",
            adapter=adapter,
            tenant_id="linas",
            idempotency_key="local-wa-failclosed",
        )
    assert result.get("success") is False
    assert "whatsapp_not_connected" in str(result.get("error") or "")
    adapter.send_text_message.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("user_id", "channel"),
    (
        ("facebook:page:psid", "facebook"),
        ("tiktok:open:id", "tiktok"),
    ),
)
async def test_social_queued_send_does_not_wait_for_provider(user_id: str, channel: str) -> None:
    enqueue = MagicMock(
        return_value={"success": True, "queued": True, "delivered": False, "delivery_status": "sending"}
    )
    slow = AsyncMock(side_effect=AssertionError("provider must not run on HTTP path"))
    extra = [
        patch("services.live_chat_operator_queue.live_chat_durable_mode", lambda: "enqueue"),
        patch("services.live_chat_operator_queue.enqueue_live_chat_operator_text", enqueue),
    ]
    if channel == "facebook":
        extra.append(patch("services.requests.delivery.deliver_meta_dm", slow))
    else:
        extra.append(patch("services.live_chat_tiktok_operator.deliver_live_chat_tiktok_operator_text", slow))
    with ExitStack() as stack:
        for cm in _send_patches(*extra, user_id=user_id):
            stack.enter_context(cm)
        started = time.monotonic()
        result = await live_chat_service.send_operator_message(
            conversation_id=f"c-{channel}",
            user_id=user_id,
            message="hello tester",
            operator_id="op1",
            adapter=MagicMock(),
            tenant_id="linas",
            idempotency_key=f"local-{channel}",
        )
        elapsed = time.monotonic() - started
    assert elapsed < 1.5
    assert result.get("success") is True
    assert result.get("queued") is True
    assert result.get("delivered") is False
    enqueue.assert_called_once()
    slow.assert_not_awaited()


@pytest.mark.asyncio
async def test_notify_skips_reconciliation_and_publishes_sent(monkeypatch: pytest.MonkeyPatch) -> None:
    published: list[tuple[str, str]] = []

    async def fake_notify(payload: dict, delivery_status: str, **_k: object) -> None:
        published.append((str(payload.get("live_chat_user_id")), delivery_status))

    monkeypatch.setattr(
        "services.live_chat_operator_delivery_status.notify_live_chat_operator_job",
        fake_notify,
    )
    from services.omnichannel.deliver import _notify_live_chat

    payload = {"live_chat_user_id": "instagram:1"}
    await _notify_live_chat(payload, "reconciliation_required")
    await _notify_live_chat(payload, "rate_limited")
    await _notify_live_chat(payload, "delivered")
    await _notify_live_chat(payload, "dead_letter", error="meta_400")
    assert published == [
        ("instagram:1", "sent"),
        ("instagram:1", "failed"),
    ]
