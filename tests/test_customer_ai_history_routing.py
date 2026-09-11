"""Channel history fallbacks must not cross-load WhatsApp into Instagram threads."""

from __future__ import annotations

import pytest

from services.customer_ai.history_store import load_history_snapshot


@pytest.mark.asyncio
async def test_history_store_whatsapp_channel_only(monkeypatch: pytest.MonkeyPatch) -> None:
    called = {"wa": 0}

    async def empty_firestore(*_a, **_k):
        return []

    def mark_wa(cid: str):
        called["wa"] += 1
        return [{"id": "wa1", "role": "user", "text": f"from-{cid}", "visible_to_customer": True}]

    monkeypatch.setattr("utils.utils_context.get_conversation_history_from_firestore", empty_firestore)
    monkeypatch.setattr("services.customer_ai.history_whatsapp.load_whatsapp_history_rows", mark_wa)
    ig = await load_history_snapshot(
        user_id="u1",
        conversation_id="wamid_lookalike_12345678",
        channel="instagram_dm",
    )
    wa = await load_history_snapshot(
        user_id="u1",
        conversation_id="wamid_lookalike_12345678",
        channel="whatsapp",
    )
    assert called["wa"] == 1
    assert ig.messages == []
    assert wa.messages[0].text == "from-wamid_lookalike_12345678"


@pytest.mark.asyncio
async def test_history_store_meta_uses_conversation_store(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.customer_ai.conversation_history import append_visible_history
    from services.customer_ai.conversation_store import reset_conversation_store_for_tests

    reset_conversation_store_for_tests()
    append_visible_history("ig-shop", "ig-thread-meta-1", [{"id": "old", "role": "user", "text": "earlier ig"}])
    called = {"wa": 0, "web": 0, "tt": 0}

    async def empty_firestore(*_a, **_k):
        return []

    monkeypatch.setattr("utils.utils_context.get_conversation_history_from_firestore", empty_firestore)
    monkeypatch.setattr(
        "services.customer_ai.history_whatsapp.load_whatsapp_history_rows",
        lambda _cid: called.__setitem__("wa", called["wa"] + 1) or [],
    )
    monkeypatch.setattr(
        "services.customer_ai.history_web.load_web_history_rows",
        lambda _cid: called.__setitem__("web", called["web"] + 1) or [],
    )
    monkeypatch.setattr(
        "services.customer_ai.history_tiktok.load_tiktok_history_rows",
        lambda _cid: called.__setitem__("tt", called["tt"] + 1) or [],
    )
    snap = await load_history_snapshot(
        user_id="u-ig",
        conversation_id="ig-thread-meta-1",
        tenant_id="ig-shop",
        channel="instagram_dm",
        current_inbound_id="now",
        current_inbound_text="price?",
    )
    assert called == {"wa": 0, "web": 0, "tt": 0}
    assert [item.text for item in snap.messages] == ["earlier ig", "price?"]


def test_media_only_turn_persists_history() -> None:
    from services.customer_ai.contracts.turn import CustomerTurn, MediaView
    from services.customer_ai.conversation_history import load_stored_history_rows, record_turn_history
    from services.customer_ai.conversation_store import reset_conversation_store_for_tests

    reset_conversation_store_for_tests()
    turn = CustomerTurn(
        tenant_id="hist-media",
        conversation_id="ig-media-only-1",
        media=MediaView(attachment_types=["image"]),
    )
    record_turn_history(turn, inbound_id="mid-img", inbound_text="")
    rows = load_stored_history_rows("hist-media", "ig-media-only-1")
    assert rows
    assert "image" in rows[0]["text"]
