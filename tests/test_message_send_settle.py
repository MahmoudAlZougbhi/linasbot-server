"""Message units settle after confirmed send, not at generate."""

from __future__ import annotations

from inspect import getsource

import pytest

from services.customer_ai.billing import apply_message_billing, settle_after_send
from services.customer_ai.contracts.reply import FinalReplyEnvelope, OutboundMessage, TurnResult
from services.customer_ai.contracts.turn import CustomerTurn
from services.membership.lot_window import current_period_id
from services.membership.message_ledger import grant_lot, remaining_messages, reset_ledger_for_tests, snapshot
from services.customer_ai.outbox import outbox_counts, recover_unsent, reset_outbox_for_tests
from services.membership.pending_settlement import reset_pending_settlements_for_tests


@pytest.fixture(autouse=True)
def _memory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LINAS_MESSAGE_STORE", "memory")
    monkeypatch.setenv("MESSAGE_BILLING_ENABLED", "true")
    reset_ledger_for_tests()
    reset_pending_settlements_for_tests()
    reset_outbox_for_tests()
    grant_lot(
        tenant_id="send-shop",
        lot_id="inc",
        kind="included",
        period_id=current_period_id(),
        amount=5,
    )


def _generated(event_id: str = "mid-1") -> tuple[CustomerTurn, TurnResult]:
    turn = CustomerTurn(
        tenant_id="send-shop",
        conversation_id="c1",
        channel="whatsapp_dm",
        event_ids=[event_id],
    )
    result = TurnResult(
        stop_reason="ok",
        ai_called=True,
        envelope=FinalReplyEnvelope(
            decision="reply",
            messages=[OutboundMessage(destination="dm", text="Hours are 9-5")],
        ),
        extra={"phase": "generate"},
    )
    return turn, result


def test_generate_holds_until_send() -> None:
    turn, result = _generated()
    billed = apply_message_billing(turn, result)
    assert billed.extra["billing_pending_send"] is True
    assert billed.extra["message_units"] == 1
    snap = snapshot("send-shop")
    assert snap.reserved == 1
    assert snap.remaining == 4
    settle_after_send(tenant_id="send-shop", operation_id="mid-1", accepted=True, channel="whatsapp")
    assert remaining_messages("send-shop") == 4
    assert snapshot("send-shop").reserved == 0


def test_failed_send_releases_hold() -> None:
    turn, result = _generated("mid-fail")
    apply_message_billing(turn, result)
    settle_after_send(tenant_id="send-shop", operation_id="mid-fail", accepted=False)
    assert remaining_messages("send-shop") == 5
    assert snapshot("send-shop").reserved == 0
    assert recover_unsent(tenant_id="send-shop") == []
    assert outbox_counts(tenant_id="send-shop")["failed"] == 1


def test_settle_matches_inbound_id_not_logical_reply() -> None:
    turn, result = _generated("mid-1")
    apply_message_billing(turn, result)
    settle_after_send(
        tenant_id="send-shop",
        operation_id="lid-other",
        accepted=True,
        extra_ids=("mid-1",),
    )
    assert remaining_messages("send-shop") == 4
    assert snapshot("send-shop").reserved == 0


def test_never_submitted_releases_ready_message_hold() -> None:
    from services.ai_reply_turn_runtime import settle_after_outbound

    turn, result = _generated("mid-ready")
    apply_message_billing(turn, result)
    settle_after_outbound(
        {
            "tenant_id": "send-shop",
            "_logical_reply_id": "lid-ready",
            "_combine_mid": "mid-ready",
            "_reply_ready": True,
            "_last_outbound_delivery": {"success": False, "retryable": False, "submitted": False},
        },
        reply="never sent",
    )
    assert remaining_messages("send-shop") == 5
    assert snapshot("send-shop").reserved == 0


def test_whatsapp_bridge_does_not_capture_before_send() -> None:
    from services.whatsapp_cloud import ai_bridge, outbound_finalization

    src = getsource(ai_bridge.maybe_generate_and_send_ai_reply)
    assert "reserve_leftover_reply" in src
    assert "credit_ledger_service.capture" not in src
    assert src.index("send_text_message") < src.index("finalize_ai_outbound_sent")
    assert "_settle_confirmed_send" in getsource(outbound_finalization.finalize_ai_outbound_sent)
    settle = getsource(outbound_finalization._settle_confirmed_send)
    assert "capture_leftover_reply" in settle
    assert "settle_after_send" in settle
    assert "intent_mid" in settle
    assert "conversation_id" in settle
    release = getsource(ai_bridge._release_reservation)
    assert "release_unsent_ai_outbound" in release
    queued = getsource(outbound_finalization.release_unsent_ai_outbound)
    assert "accepted=False" in queued
    from services.whatsapp_cloud.delivery_retry import send_canonical_intent

    retry = getsource(send_canonical_intent)
    assert "release_unsent_ai_outbound" in retry
    assert retry.index("if not ambiguous") < retry.rindex("release_unsent_ai_outbound")


def test_comment_and_omni_settle_after_delivery() -> None:
    from services.meta_comment_brain_send import send_comment_destinations
    from services.omnichannel.deliver import _finish_success
    from services.tiktok_business.comment_ai import process_tiktok_comment_ai

    comment = getsource(send_comment_destinations)
    assert "_settle_comment_send" in comment
    from services.meta_comment_replies import process_meta_comment_event

    public = getsource(process_meta_comment_event)
    assert "_settle_generated_comment" in public
    assert "accepted=True" in public
    assert "accepted=False" in public
    deliver = getsource(_finish_success)
    assert "settle_after_send" in deliver
    assert "_message_settle_ops" in deliver
    from services.web_chat.processor_turn_finalize import complete_captured_turn

    web = getsource(complete_captured_turn)
    assert "web_inbound_message_id" in web
    assert "extra_ids" in web
    tiktok = getsource(process_tiktok_comment_ai)
    assert "_settle_comment_send" in tiktok
    assert "accepted=True" in tiktok
    assert "accepted=False" in tiktok
    from services.omnichannel.deliver import _release_credits_if_never_submitted

    release = getsource(_release_credits_if_never_submitted)
    assert "release_leftover_reply" in release
    assert "accepted=False" in release
    assert "message_operation_id" in release
    assert "credit_ledger_service.release" not in release
    from services.ai_reply_turn_runtime import finalize_delivery as finalize_meta_delivery

    meta = getsource(finalize_meta_delivery)
    assert "_release_unused_hold" in meta
    assert meta.index("success") < meta.index("_release_unused_hold")


def test_omni_settle_matches_provider_mid_not_row_id() -> None:
    from types import SimpleNamespace

    from services.omnichannel.deliver import _message_settle_ops

    inbound = SimpleNamespace(
        provider_event_id="wamid.omni-1",
        payload={"text": "hours?"},
    )
    primary, extras = _message_settle_ops(
        inbound=inbound,
        inbound_id="row-uuid",
        reservation="leftover-1",
    )
    assert primary == "wamid.omni-1"
    assert "row-uuid" in extras
    turn, result = _generated("wamid.omni-1")
    apply_message_billing(turn, result)
    settle_after_send(
        tenant_id="send-shop",
        operation_id="row-uuid",
        accepted=True,
        extra_ids=extras,
    )
    assert remaining_messages("send-shop") == 4
    assert snapshot("send-shop").reserved == 0


def test_web_chat_settle_matches_inbound_hash() -> None:
    from services.customer_ai.history_ids import web_inbound_message_id

    mid = web_inbound_message_id("web:sess", "hours?")
    turn, result = _generated(mid)
    apply_message_billing(turn, result)
    settle_after_send(
        tenant_id="send-shop",
        operation_id="visitor:client-key",
        accepted=True,
        extra_ids=(mid,),
    )
    assert remaining_messages("send-shop") == 4
    assert snapshot("send-shop").reserved == 0


def test_web_chat_fence_releases_inbound_hold() -> None:
    from services.customer_ai.history_ids import web_inbound_message_id
    from services.web_chat.operation_fence import fenced_failure_release, release_web_chat_message_hold

    mid = web_inbound_message_id("web:sess", "hours?")
    turn, result = _generated(mid)
    apply_message_billing(turn, result)
    release_web_chat_message_hold(
        tenant_id="send-shop",
        operation_key="visitor:client-key",
        conversation_id="web:sess",
        user_text="hours?",
    )
    assert remaining_messages("send-shop") == 5
    assert snapshot("send-shop").reserved == 0
    fence = getsource(fenced_failure_release)
    assert "release_web_chat_message_hold" in fence
    assert "conversation_id" in fence


def test_web_chat_fence_does_not_invent_inbound_text() -> None:
    from services.customer_ai.history_ids import web_inbound_message_id
    from services.web_chat.operation_fence import release_web_chat_message_hold

    mid = web_inbound_message_id("web:sess", "hours?")
    turn, result = _generated(mid)
    apply_message_billing(turn, result)
    release_web_chat_message_hold(tenant_id="send-shop", operation_key="visitor:client-key")
    assert remaining_messages("send-shop") == 4
    assert snapshot("send-shop").reserved == 1


def test_tiktok_dm_settle_matches_minted_inbound() -> None:
    from services.customer_ai.history_ids import bind_dm_ids
    from services.tiktok_business.messaging import _maybe_ai_dm, _settle_tiktok_dm_send

    _conv, mid = bind_dm_ids(conversation_id="tt-conv", message_id="", message="hours?")
    assert mid
    turn, result = _generated(mid)
    apply_message_billing(turn, result)
    _settle_tiktok_dm_send(
        tenant_id="send-shop",
        snapshot={"conversation_id": "tt-conv"},
        leftover_rid="tiktok:tt-conv",
        brain_mid=mid,
        accepted=True,
    )
    assert remaining_messages("send-shop") == 4
    assert snapshot("send-shop").reserved == 0
    dm = getsource(_maybe_ai_dm)
    assert "bind_dm_ids" in dm
    assert "accepted=False" in dm


def test_whatsapp_cloud_fail_releases_message_hold() -> None:
    from services.whatsapp_cloud.outbound_finalization import release_unsent_ai_outbound

    turn, result = _generated("wamid.fail")
    apply_message_billing(turn, result)
    release_unsent_ai_outbound(
        tenant_id="send-shop",
        inbound_mid="wamid.fail",
        inbound_id="row-uuid",
    )
    assert remaining_messages("send-shop") == 5
    assert snapshot("send-shop").reserved == 0


def test_whatsapp_settle_uses_intent_mid_when_inbound_empty() -> None:
    from services.whatsapp_cloud.outbound_finalization import _settle_confirmed_send

    turn, result = _generated("wamid.from-intent")
    apply_message_billing(turn, result)
    _settle_confirmed_send(
        tenant_id="send-shop",
        inbound_mid="",
        provider_wamid="wamid.out",
        triggering_inbound_id="row-uuid",
        conversation_id="wa-conv",
        intent_mid="wamid.from-intent",
    )
    assert remaining_messages("send-shop") == 4
    assert snapshot("send-shop").reserved == 0


def test_sfu_revalidate_uses_live_customer_reply() -> None:
    from services.smart_followup.worker_job import process_one_followup_job

    src = getsource(process_one_followup_job)
    assert "customer_replied=" in src
    assert "opt_out=" in src
    assert "last_inbound" in src
    assert "settle_followup_from_snapshot" in src
    assert "_release_message_followup" in src
    assert "_finish_attempt_holds" in src
    from services.smart_followup.worker_job import _finish_attempt_holds

    assert "accepted=sent" in getsource(_finish_attempt_holds)
    assert 'snapshot.get("channel") == "web_chat"' not in src


def test_sfu_settle_matches_minted_followup_id() -> None:
    from services.smart_followup.billing_ids import followup_operation_ids, settle_followup_from_snapshot

    job = {
        "idempotency_key": "seq-1:2",
        "conversation_id": "wa-conv",
        "goal": "gentle_check_in",
    }
    primary, extras = followup_operation_ids(job)
    assert primary == "sfu:seq-1:2"
    assert "seq-1:2" in extras
    assert "sfu:wa-conv:gentle_check_in" in extras
    turn, result = _generated("sfu:seq-1:2")
    apply_message_billing(turn, result)
    settle_followup_from_snapshot("send-shop", job, accepted=True)
    assert remaining_messages("send-shop") == 4
    assert snapshot("send-shop").reserved == 0


def test_omni_generate_fail_releases_brain_hold() -> None:
    from services.omnichannel.generate import handle_omnichannel_generate
    from services.omnichannel.message_hold import release_unsent_omni_hold

    src = getsource(handle_omnichannel_generate)
    assert "release_unsent_omni_hold" in src
    assert src.count("release_unsent_omni_hold") >= 3
    turn, result = _generated("wamid.omni-fail")
    apply_message_billing(turn, result)
    release_unsent_omni_hold(
        tenant_id="send-shop",
        payload={"provider_message_id": "wamid.omni-fail"},
        conversation_key="ig:thread",
        channel="instagram",
    )
    assert remaining_messages("send-shop") == 5
    assert snapshot("send-shop").reserved == 0


def test_reconcile_settles_alias_operation_id() -> None:
    from services.membership.pending_settlement import record_pending_after_send
    from services.membership.reservation_reconcile import run_reservation_reconcile

    turn, result = _generated("mid-alias")
    apply_message_billing(turn, result)
    record_pending_after_send(
        tenant_id="send-shop",
        reservation_id="row-uuid",
        operation_id="row-uuid",
        billing_policy="message_units",
        provider_message_id="mid-alias",
        channel="instagram",
    )
    from services.membership.pending_settlement import upsert

    upsert(
        tenant_id="send-shop",
        reservation_id="row-uuid",
        operation_id="row-uuid",
        billing_policy="message_units",
        state="pending_settlement",
        send_status="sent",
        provider_message_id="mid-alias",
        extra={"candidate_ids": ["mid-alias"]},
    )
    report = run_reservation_reconcile()
    assert report["settled"] >= 1
    assert remaining_messages("send-shop") == 4
    assert snapshot("send-shop").reserved == 0


def test_empty_generate_and_exception_release_message_hold() -> None:
    from services.ai_reply_turn_runtime import _message_settle_ids, on_ai_failed, on_ai_generated

    turn, result = _generated("mid-empty")
    apply_message_billing(turn, result)
    on_ai_generated(
        {
            "user_data": {
                "tenant_id": "send-shop",
                "_logical_reply_id": "lid-empty",
                "_combine_mid": "mid-empty",
            },
            "bot_reply_text": "",
        }
    )
    assert remaining_messages("send-shop") == 5
    assert snapshot("send-shop").reserved == 0

    turn, result = _generated("mid-exc")
    apply_message_billing(turn, result)
    on_ai_failed(
        {
            "user_data": {
                "tenant_id": "send-shop",
                "_logical_reply_id": "lid-exc",
                "_source_message_id": "mid-exc",
            }
        }
    )
    assert remaining_messages("send-shop") == 5
    assert snapshot("send-shop").reserved == 0
    assert "on_ai_failed" in getsource(on_ai_generated)
    assert "_settle_unsent_message" in getsource(on_ai_failed)
    assert "conversation_id_from_user_data" in getsource(_message_settle_ids)


def test_sfu_generation_fail_releases_minted_hold() -> None:
    from services.smart_followup.billing_ids import settle_followup_from_snapshot

    turn, result = _generated("sfu:wa-conv:gentle_check_in")
    apply_message_billing(turn, result)
    settle_followup_from_snapshot(
        "send-shop",
        {"conversation_id": "wa-conv", "goal": "gentle_check_in"},
        accepted=False,
    )
    assert remaining_messages("send-shop") == 5
    assert snapshot("send-shop").reserved == 0


def test_hold_policy_does_not_tag_message_holds_as_leftover(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.membership.hold_policy import hold_billing_policy

    assert hold_billing_policy(leftover_reservation_id="rid-1") == "legacy_credits"
    assert hold_billing_policy(leftover_reservation_id=None) == "message_units"
    monkeypatch.delenv("MESSAGE_BILLING_ENABLED", raising=False)
    assert hold_billing_policy(leftover_reservation_id=None) == "legacy_credits"


def test_ambiguous_holds_use_hold_policy_not_leftover_only() -> None:
    from services.membership.pending_settlement import list_pending
    from services.tiktok_business import messaging as tiktok_messaging
    from services.whatsapp_cloud.ai_bridge import _hold_after_ambiguous_send

    hold = getsource(_hold_after_ambiguous_send)
    assert "hold_billing_policy" in hold
    assert "unknown_send_outcome" in hold
    assert "hold_failed_capture_after_send" not in hold
    assert "hold_billing_policy" in getsource(tiktok_messaging)
    _hold_after_ambiguous_send("send-shop", None, "wamid.amb-1")
    rows = [item for item in list_pending() if item.operation_id == "wamid.amb-1"]
    assert rows
    assert rows[0].billing_policy == "message_units"
    assert rows[0].state == "unresolved"
    assert rows[0].send_status != "sent"
