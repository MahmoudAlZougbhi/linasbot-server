"""Failed Instagram Live Chat sends must undo the pause they just created."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.live_chat_service import live_chat_service


@pytest.mark.asyncio
async def test_failed_social_send_undoes_fresh_manual_pause() -> None:
    pause_result = MagicMock(activated=True, already_active=False, control_epoch=3)
    resume = AsyncMock(return_value=MagicMock(control_epoch=4, already_active=False, audit_recorded=False))

    with (
        patch(
            "services.live_chat_service_operator._try_acquire_operator_send_idempotency",
            new_callable=AsyncMock,
            return_value=(True, None),
        ),
        patch("services.live_chat_service_operator._release_operator_idempotency_lock", new_callable=AsyncMock),
        patch("utils.utils.get_canonical_user_id_and_phone", return_value=("instagram:1761", None)),
        patch("utils.utils.get_firestore_db", return_value=None),
        patch("utils.utils.save_conversation_message_to_firestore", new_callable=AsyncMock),
        patch(
            "services.requests.manual_mode.activate_manual_mode",
            new_callable=AsyncMock,
            return_value=pause_result,
        ),
        patch(
            "services.live_chat_operator_social_delivery.deliver_social_operator_text",
            new_callable=AsyncMock,
            return_value={"success": False, "delivered": False, "error": "meta_send_failed"},
        ),
        patch("services.requests.manual_mode.resume_manual_mode", resume),
        patch.object(live_chat_service, "_refresh_index_for_conversation", new_callable=AsyncMock),
    ):
        result = await live_chat_service.send_operator_message(
            conversation_id="c-ig-1",
            user_id="instagram:1761",
            message="hello tester",
            operator_id="op1",
            adapter=MagicMock(),
            tenant_id=None,
        )

    assert result.get("success") is False
    assert "delivery failed" in str(result.get("error") or "").lower()
    assert result.get("manual_mode_undone_after_failed_delivery") is True
    assert result.get("status") == "bot"
    resume.assert_awaited_once()


@pytest.mark.asyncio
async def test_instagram_send_does_not_open_whatsapp_postgres() -> None:
    def boom(*_a, **_k):
        raise AssertionError("WhatsApp Postgres must not open for Instagram Live Chat")

    with (
        patch(
            "services.live_chat_service_operator._try_acquire_operator_send_idempotency",
            new_callable=AsyncMock,
            return_value=(True, None),
        ),
        patch("services.live_chat_service_operator._release_operator_idempotency_lock", new_callable=AsyncMock),
        patch("utils.utils.get_canonical_user_id_and_phone", return_value=("instagram:1761", None)),
        patch("utils.utils.get_firestore_db", return_value=None),
        patch("utils.utils.save_conversation_message_to_firestore", new_callable=AsyncMock),
        patch(
            "services.requests.manual_mode.activate_manual_mode",
            new_callable=AsyncMock,
            return_value=MagicMock(activated=True, already_active=False, control_epoch=None),
        ),
        patch(
            "services.live_chat_operator_social_delivery.deliver_social_operator_text",
            new_callable=AsyncMock,
            return_value={"success": True, "delivered": True},
        ),
        patch.object(live_chat_service, "_refresh_index_for_conversation", new_callable=AsyncMock),
        patch("db.session.whatsapp_session", side_effect=boom),
    ):
        result = await live_chat_service.send_operator_message(
            conversation_id="c-ig-1",
            user_id="instagram:1761",
            message="hello tester",
            operator_id="op1",
            adapter=MagicMock(),
            tenant_id="linas",
        )
    assert result.get("success") is True
    assert result.get("status") == "human"


@pytest.mark.asyncio
async def test_social_send_exception_undoes_fresh_pause() -> None:
    resume = AsyncMock(return_value=MagicMock(control_epoch=4, already_active=False, audit_recorded=False))
    with (
        patch(
            "services.live_chat_service_operator._try_acquire_operator_send_idempotency",
            new_callable=AsyncMock,
            return_value=(True, None),
        ),
        patch("services.live_chat_service_operator._release_operator_idempotency_lock", new_callable=AsyncMock),
        patch("utils.utils.get_canonical_user_id_and_phone", return_value=("instagram:1761", None)),
        patch("utils.utils.get_firestore_db", return_value=None),
        patch("utils.utils.save_conversation_message_to_firestore", new_callable=AsyncMock),
        patch(
            "services.requests.manual_mode.activate_manual_mode",
            new_callable=AsyncMock,
            return_value=MagicMock(activated=True, already_active=False, control_epoch=3),
        ),
        patch(
            "services.live_chat_operator_social_delivery.deliver_social_operator_text",
            new_callable=AsyncMock,
            side_effect=TimeoutError("graph hung"),
        ),
        patch("services.requests.manual_mode.resume_manual_mode", resume),
        patch.object(live_chat_service, "_refresh_index_for_conversation", new_callable=AsyncMock),
    ):
        result = await live_chat_service.send_operator_message(
            conversation_id="c-ig-1",
            user_id="instagram:1761",
            message="hello tester",
            operator_id="op1",
            adapter=MagicMock(),
            tenant_id="linas",
        )
    assert result.get("success") is False
    assert result.get("status") == "bot"
    assert result.get("manual_mode_undone_after_failed_delivery") is True
    resume.assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_social_image_send_undoes_fresh_pause() -> None:
    resume = AsyncMock(return_value=MagicMock(control_epoch=4, already_active=False, audit_recorded=False))
    with (
        patch(
            "services.live_chat_service_operator._try_acquire_operator_send_idempotency",
            new_callable=AsyncMock,
            return_value=(True, None),
        ),
        patch("services.live_chat_service_operator._release_operator_idempotency_lock", new_callable=AsyncMock),
        patch("utils.utils.get_canonical_user_id_and_phone", return_value=("instagram:1761", None)),
        patch("utils.utils.get_firestore_db", return_value=None),
        patch("utils.utils.save_conversation_message_to_firestore", new_callable=AsyncMock),
        patch(
            "utils.utils.upload_base64_to_firebase_storage",
            new_callable=AsyncMock,
            return_value="https://cdn/x.jpg",
        ),
        patch(
            "services.requests.manual_mode.activate_manual_mode",
            new_callable=AsyncMock,
            return_value=MagicMock(activated=True, already_active=False, control_epoch=3),
        ),
        patch(
            "services.live_chat_operator_social_delivery.deliver_social_operator_media",
            new_callable=AsyncMock,
            return_value={"success": False, "delivered": False, "error": "meta_media_failed"},
        ),
        patch("services.requests.manual_mode.resume_manual_mode", resume),
        patch.object(live_chat_service, "_refresh_index_for_conversation", new_callable=AsyncMock),
    ):
        result = await live_chat_service.send_operator_message(
            conversation_id="c-ig-1",
            user_id="instagram:1761",
            message="YmFzZTY0",
            operator_id="op1",
            adapter=MagicMock(),
            message_type="image",
            tenant_id="linas",
        )
    assert result.get("success") is False
    assert result.get("status") == "bot"
    assert result.get("manual_mode_undone_after_failed_delivery") is True
    resume.assert_awaited_once()


@pytest.mark.asyncio
async def test_resume_ai_skips_whatsapp_postgres_for_instagram() -> None:
    def boom(*_a, **_k):
        raise AssertionError("WhatsApp Postgres must not open for Instagram Resume AI")

    resume = AsyncMock(return_value=MagicMock(control_epoch=5, already_active=False, audit_recorded=False))
    with (
        patch("db.session.whatsapp_session", side_effect=boom),
        patch("services.requests.manual_mode.resume_manual_mode", resume),
        patch.object(
            live_chat_service,
            "release_conversation",
            new_callable=AsyncMock,
            return_value={"success": True},
        ),
        patch.object(live_chat_service, "_refresh_index_for_conversation", new_callable=AsyncMock),
    ):
        result = await live_chat_service.resume_ai_conversation(
            conversation_id="c-ig-1",
            user_id="instagram:1761",
            operator_id="op1",
            tenant_id="linas",
        )
    assert result.get("success") is True
    assert result.get("status") == "bot"
    resume.assert_awaited_once()
