"""Message-ledger follow-up and WhatsApp credit gates. Flags stay off by default."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from services.membership.reservation_gc import _created_at
from services.web_chat.followup_message_ledger import credit_reservation_required, followup_uses_message_ledger


def test_flags_stay_off_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MESSAGE_BILLING_ENABLED", raising=False)
    assert followup_uses_message_ledger() is False
    assert credit_reservation_required("") is True
    assert credit_reservation_required("cred-1") is False


def test_message_billing_skips_web_credit_reservation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MESSAGE_BILLING_ENABLED", "true")
    assert followup_uses_message_ledger() is True
    assert credit_reservation_required("") is False


def test_web_adapter_and_delivery_honor_message_ledger() -> None:
    from inspect import getsource

    from services.smart_followup.adapters import web as web_adapter
    from services.web_chat import followup_delivery
    from services.whatsapp_cloud import ai_bridge

    assert "credit_reservation_required" in getsource(web_adapter.WebFollowUpAdapter.send_followup)
    assert "followup_uses_message_ledger" in getsource(followup_delivery._preflight_reservation_or_resume)
    assert "followup_uses_message_ledger" in getsource(followup_delivery._resolve_bound_reservation)
    assert "followup_uses_message_ledger" in getsource(followup_delivery._finalize_followup_billing)
    assert "settle_followup_from_snapshot" in getsource(followup_delivery._finalize_followup_billing)
    src = getsource(ai_bridge.maybe_generate_and_send_ai_reply)
    assert "message_billing_enabled" in src
    assert src.index("if not message_billing_enabled()") < src.index("reserve_leftover_reply")
    assert "credit_ledger_service.capture" not in src


def test_reservation_insert_writes_created_at() -> None:
    from inspect import getsource

    from services.membership import message_ledger_pg

    src = getsource(message_ledger_pg._insert_reservation)
    assert "created_at" in src
    assert ":created_at" in src


def test_gc_parses_datetime_created_at() -> None:
    stamp = datetime.now(UTC) - timedelta(hours=2)
    assert _created_at(stamp) == stamp
    assert _created_at(stamp.isoformat()) is not None
    assert _created_at("") is None
    assert _created_at(None) is None


def test_meta_comment_forwards_caption_when_present() -> None:
    from inspect import getsource

    from services import meta_comment_replies

    src = getsource(meta_comment_replies)
    assert 'event.get("caption")' in src
    assert 'event.get("parent_comment")' in src
    assert 'parent_comment": str(event.get("parent_id")' not in src


def test_web_live_handle_skips_credit_ledger(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.web_chat.credit_fsm import CreditFsmState, WebChatCreditHandle
    from services.web_chat.followup_message_ledger import message_reservation_id

    monkeypatch.setenv("MESSAGE_BILLING_ENABLED", "true")
    handle = WebChatCreditHandle(tenant_id="biz", reservation_id=None, request_id="web:live:1")
    handle.reserve()
    assert handle.reservation_id == message_reservation_id("web:live:1")
    assert handle.state == CreditFsmState.RESERVED
    handle.capture()
    assert handle.state == CreditFsmState.CAPTURED
    released = WebChatCreditHandle(tenant_id="biz", reservation_id=None, request_id="web:live:2")
    released.reserve()
    assert released.release() is True
    assert released.state == CreditFsmState.RELEASED


def test_reserve_before_ai_skips_credits_when_billing_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services.ai_reply_credit_gate import reserve_before_ai
    from services.ai_reply_lifecycle import begin_turn

    monkeypatch.setenv("MESSAGE_BILLING_ENABLED", "true")
    called = {"n": 0}

    def boom(**_kwargs):
        called["n"] += 1
        raise AssertionError("credit reserve must not run")

    monkeypatch.setattr("services.credit_ledger_service.credit_ledger_service.reserve", boom)
    turn = begin_turn(tenant_id="clinic", channel="instagram", external_inbound_id="mid-bill-1")
    assert reserve_before_ai(turn) is None
    assert called["n"] == 0
    assert turn.state == "AI_PROCESSING"


def test_try_reserve_uses_messages_not_credits(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.ai_reply_turn_runtime import try_reserve_for_ai

    monkeypatch.setenv("MESSAGE_BILLING_ENABLED", "true")
    monkeypatch.setattr("services.membership.generative_gate.generative_ai_blocked", lambda _tid, **_kw: False)
    called = {"n": 0}

    def boom(**_kwargs):
        called["n"] += 1
        raise AssertionError("credit reserve must not run")

    monkeypatch.setattr("services.credit_ledger_service.credit_ledger_service.reserve", boom)
    user_data = {"tenant_id": "clinic", "_source_message_id": "mid-bill-2", "channel": "instagram"}
    assert try_reserve_for_ai(user_data) is True
    assert called["n"] == 0
    assert user_data.get("_ai_credit_blocked") is not True


def test_preview_turn_does_not_hold_messages(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.customer_ai.billing import apply_message_billing, owner_preview_turn, reserve_generative
    from services.customer_ai.contracts.reply import FinalReplyEnvelope, OutboundMessage, TurnResult
    from services.customer_ai.contracts.turn import CustomerTurn

    monkeypatch.setenv("MESSAGE_BILLING_ENABLED", "true")
    turn = CustomerTurn(
        tenant_id="clinic",
        conversation_id="preview:clinic",
        invocation_kind="followup",
        followup_goal="gentle_check_in",
        event_ids=["sfu:preview:clinic:gentle_check_in"],
    )
    assert owner_preview_turn(turn) is True
    assert reserve_generative(turn) is None
    result = apply_message_billing(
        turn,
        TurnResult(
            stop_reason="ok",
            ai_called=True,
            envelope=FinalReplyEnvelope(
                decision="reply",
                messages=[OutboundMessage(destination="dm", text="checking in")],
            ),
        ),
    )
    assert result.stop_reason == "ok"
    assert result.extra.get("billing_pending_send") is not True


def test_omni_and_request_persist_stay_honest() -> None:
    from inspect import getsource

    from services.customer_ai.actions.requests import persist_request
    from services.omnichannel import deliver
    from services.omnichannel.channel_web_chat import generate_web_chat_reply
    from services.omnichannel.channel_whatsapp import generate_whatsapp_reply

    persist_src = getsource(persist_request)
    assert "published_configuration_version" in persist_src
    assert "merge_fields_for_persist" in persist_src
    assert "configuration_version=current_revision" not in persist_src
    wa_src = getsource(generate_whatsapp_reply)
    assert "reserve_leftover_reply" in wa_src
    web_src = getsource(generate_web_chat_reply)
    assert "message_billing_enabled" in web_src
    deliver_src = getsource(deliver._finish_success)
    assert "message_billing_enabled" in deliver_src
    assert deliver_src.index("if not message_billing_enabled()") < deliver_src.index(
        "capture_leftover_reply"
    )


def test_live_and_preview_gates_are_wired() -> None:
    from inspect import getsource

    from modules import whatsapp_smart_followup_api
    from services.ai_reply_credit_gate import reserve_before_ai
    from services.web_chat.credit_fsm import WebChatCreditHandle
    from services.web_chat.processor_v2_reply import generate_web_chat_reply_text

    reserve_src = getsource(reserve_before_ai)
    assert "message_billing_enabled" in reserve_src
    assert reserve_src.index("if message_billing_enabled()") < reserve_src.index("credit_ledger_service.reserve")
    handle_src = getsource(WebChatCreditHandle.reserve)
    assert "followup_uses_message_ledger" in handle_src
    preview_src = getsource(whatsapp_smart_followup_api.smart_followup_preview)
    assert "uses_credits" in preview_src
    assert "credit_ledger_service.reserve" not in preview_src
    assert "insufficient_messages" in getsource(generate_web_chat_reply_text)


def test_settle_reserved_credits_captures_or_releases(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.ai_reply_turn_runtime import settle_reserved_credits

    calls: list[tuple] = []
    monkeypatch.setattr(
        "services.ai_reply_turn_runtime.on_ai_generated",
        lambda ctx: calls.append(("gen", ctx.get("bot_reply_text"))),
    )
    monkeypatch.setattr(
        "services.ai_reply_turn_runtime.on_ai_failed",
        lambda ctx: calls.append(("fail",)),
    )
    settle_reserved_credits({}, reply="hello")
    settle_reserved_credits({"_logical_reply_id": "lid-1"}, reply="hello")
    settle_reserved_credits({"_logical_reply_id": "lid-1"}, reply="")
    assert calls == [("gen", "hello"), ("fail",)]


def test_sfu_worker_settles_leftover_credits() -> None:
    from inspect import getsource

    from services.smart_followup import worker_job

    settle = getsource(worker_job._settle_leftover)
    assert "_capture(tenant_id, reservation_id)" in settle
    assert "hold_failed_capture_after_send" in settle
    assert "_release(tenant_id, reservation_id)" in settle
    src = getsource(worker_job.process_one_followup_job)
    assert src.count("_finish_attempt_holds(") >= 2
    assert "_settle_leftover" in getsource(worker_job._finish_attempt_holds)
    assert src.count("_release(tenant_id, reservation_id)") >= 4
    assert "_capture(tenant_id, reservation_id)" in src
    recon = src.index("reconciliation_required")
    assert src.index("unknown_send_outcome", recon)
    assert "hold_failed_capture_after_send" in src[recon:]
    assert "hold_billing_policy" in src[recon:]


def test_leftover_reserve_skips_when_billing_on(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.customer_ai.leftover_reserve import reserve_leftover_reply

    monkeypatch.setenv("MESSAGE_BILLING_ENABLED", "true")
    assert reserve_leftover_reply(tenant_id="shop", request_id="omni:1", operation_type="omni") is None


def test_delayed_text_settles_leftover_credits() -> None:
    from inspect import getsource

    from handlers import text_handlers_delayed

    src = getsource(text_handlers_delayed._delayed_process_messages)
    assert "try_reserve_for_ai" in src
    assert src.count("settle_reserved_credits") >= 2
    assert 'if not user_data.get("_credit_captured_for_turn")' in src


def test_phase2_settles_cm_and_halt_paths() -> None:
    from inspect import getsource

    from handlers.text_handlers_respond_phase2 import text_handlers_respond_phase2

    src = getsource(text_handlers_respond_phase2)
    assert src.count("settle_after_outbound") >= 3
    assert src.count("settle_reserved_credits") >= 1
    assert "engine_removed" in src
    halt = src.index('{"insufficient_credits", "insufficient_messages", "engine_removed"}')
    assert src.index("settle_reserved_credits(user_data)", halt) < src.index("return _PHASE_HALT", halt)


def test_reserve_generative_skips_leftover_conversation_pin(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.customer_ai.billing import reserve_generative
    from services.customer_ai.contracts.turn import CustomerTurn
    from services.customer_ai.leftover_reserve import _pin, reset_leftover_pins_for_tests
    from services.membership.lot_window import current_period_id
    from services.membership.message_ledger import grant_lot, remaining_messages, reset_ledger_for_tests

    reset_ledger_for_tests()
    reset_leftover_pins_for_tests()
    monkeypatch.setenv("LINAS_MESSAGE_STORE", "memory")
    monkeypatch.setenv("MESSAGE_BILLING_ENABLED", "true")
    grant_lot(tenant_id="pin-shop", lot_id="inc", kind="included", period_id=current_period_id(), amount=2)
    _pin("pin-shop", "conv-leftover")
    turn = CustomerTurn(tenant_id="pin-shop", conversation_id="conv-leftover", event_ids=["evt-new"])
    assert reserve_generative(turn) is None
    assert remaining_messages("pin-shop") == 2


def test_settle_after_send_does_not_mint_when_leftover_owns_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services.customer_ai.billing import settle_after_send
    from services.customer_ai.leftover_reserve import _pin, reset_leftover_pins_for_tests
    from services.membership.lot_window import current_period_id
    from services.membership.message_ledger import grant_lot, remaining_messages, reset_ledger_for_tests

    reset_ledger_for_tests()
    reset_leftover_pins_for_tests()
    monkeypatch.setenv("LINAS_MESSAGE_STORE", "memory")
    monkeypatch.setenv("MESSAGE_BILLING_ENABLED", "true")
    grant_lot(tenant_id="pin-shop", lot_id="inc", kind="included", period_id=current_period_id(), amount=2)
    _pin("pin-shop", "mid-leftover")
    settle_after_send(tenant_id="pin-shop", operation_id="mid-leftover", accepted=True, channel="web_chat")
    assert remaining_messages("pin-shop") == 2


def test_followup_leftover_pins_include_conversation() -> None:
    from inspect import getsource

    from services.smart_followup import worker_job
    from services.smart_followup.billing_ids import leftover_followup_pins

    class _Job:
        conversation_id = "conv-1"
        goal = "nudge"
        idempotency_key = "sfu:seq:1"

    pins = leftover_followup_pins(_Job())
    assert "conv-1" in pins
    assert "sfu:conv-1:nudge" in pins
    src = getsource(worker_job.process_one_followup_job)
    assert "remember_leftover_hold" in src
    assert "leftover_followup_pins" in src
