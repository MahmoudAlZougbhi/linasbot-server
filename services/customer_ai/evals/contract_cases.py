"""Offline contract checks. No live provider spend and no activation flags."""

from __future__ import annotations

from typing import Any

from services.customer_ai.actions.confirm import confirmation_valid, looks_like_confirmation
from services.customer_ai.billing import classify_result, owner_preview_turn
from services.customer_ai.contracts.reply import FinalReplyEnvelope, OutboundMessage, TurnResult
from services.customer_ai.contracts.turn import CustomerTurn
from services.customer_ai.greeting import evaluate_greeting
from services.customer_ai.history import build_history_snapshot
from services.customer_ai.conversation_history import append_visible_history, load_stored_history_rows
from services.customer_ai.conversation_store import reset_conversation_store_for_tests
from services.customer_ai.actions.requests import request_source_channel
from services.customer_ai.history_ids import (
    conversation_id_for_brain,
    message_id_for_brain,
    web_inbound_message_id,
)
from services.customer_ai.history_tiktok import provider_conversation_id
from services.customer_ai.history_web import session_id_from_conversation
from services.customer_ai.policies.restricted import refuse_text
from services.customer_ai.visual import visual_retrieval_decision
from services.cm.schemas import RestrictedTopic
from services.membership.feature_entitlements import channel_flags_for_plan, comments_allowed_for_plan, faq_limits_for_plan
from services.membership.message_flags import activation_flags_report
from services.customer_ai.planner.heuristic import plan_message
from services.customer_ai.gates import evaluate_gates
from services.customer_ai.turn_pipeline import inbound_task_text
from services.customer_ai.contracts.turn import MediaView
from services.membership.message_policy import message_units_for
from inspect import getsource


def _turn(**kwargs: Any) -> CustomerTurn:
    return CustomerTurn(tenant_id="eval", **kwargs)


def _generate_holds_until_send() -> bool:
    from handlers.text_handlers_respond_phase2 import text_handlers_respond_phase2
    from services.ai_reply_turn_runtime import _capture_ready_turn, on_ai_generated, settle_after_outbound
    from services.customer_ai.billing import settle_after_send
    from services.smart_followup.worker_job import process_one_followup_job
    from services.whatsapp_cloud.ai_bridge import _release_reservation

    generated = getsource(on_ai_generated)
    phase2 = getsource(text_handlers_respond_phase2)
    after = getsource(settle_after_outbound)
    capture = getsource(_capture_ready_turn)
    settle = getsource(settle_after_send)
    return (
        "capture_after_reply_persisted" not in generated
        and "_reply_ready" in generated
        and "settle_after_outbound" in phase2
        and "_release_unused_hold" in after
        and "message_id_for_brain" in capture
        and "_candidate_ops" in settle
        and "release_unsent_ai_outbound" in getsource(_release_reservation)
        and "settle_followup_from_snapshot" in getsource(process_one_followup_job)
    )


def _cloud_inbound_hydrates() -> bool:
    from services.whatsapp_cloud.webhook_processor import _process_one_event

    src = getsource(_process_one_event)
    return src.index("hydrate_cloud_inbound_snapshot") < src.index("maybe_generate_and_send_ai_reply")


def _tiktok_media_reaches_brain() -> bool:
    from services.omnichannel import generate as omni_generate
    from services.tiktok_business.messaging import handle_messaging_webhook

    hook = getsource(handle_messaging_webhook)
    omni = getsource(omni_generate)
    return (
        "hydrate_tiktok_inbound_media" in hook
        and "inbound_media.get(\"attachment_types\")" in hook
        and "inbound_media=inbound_media or None" in omni
    )


def _omni_generate_releases_unsent() -> bool:
    from services.omnichannel.generate import handle_omnichannel_generate
    from services.omnichannel.channel_whatsapp import generate_whatsapp_reply
    from services.customer_ai.test_lab import run_lab_turn

    return (
        "release_unsent_omni_hold" in getsource(handle_omnichannel_generate)
        and "release_unsent_omni_hold" in getsource(generate_whatsapp_reply)
        and "settle_after_send" in getsource(run_lab_turn)
    )


def _comment_threads_share_fallback() -> bool:
    from services.customer_ai.history_ids import comment_conversation_id
    from services.customer_ai.runtime import run_customer_ai_comment

    fallback = comment_conversation_id(
        tenant_id="t",
        channel="instagram_comment",
        post_id="p1",
    )
    return fallback == "comment:t:instagram_comment:p1" and "comment_conversation_id" in getsource(run_customer_ai_comment)


def _history_routes_by_channel() -> bool:
    from services.customer_ai.history_store import load_history_snapshot

    src = getsource(load_history_snapshot)
    return (
        "_looks_whatsapp" in src
        and "_looks_web" in src
        and "_looks_tiktok" in src
        and "_looks_meta" in src
        and "load_stored_history_rows" in src
    )


def _legacy_photo_fetches_ssrf_safe() -> bool:
    from handlers.photo_handlers import handle_photo_message

    src = getsource(handle_photo_message)
    return (
        "store_inbound_image_from_url" in src
        and src.index("store_inbound_image_from_url") < src.index("httpx.AsyncClient")
        and "record_pending_provider" in src
        and "0.01" not in src
        and "0.03" not in src
    )


def _index_seeds_from_pending() -> bool:
    from services.membership.reservation_reconcile import watch_stale_legacy_credits
    from services.membership.credit_reservation_scan import known_credit_tenant_ids

    src = getsource(watch_stale_legacy_credits)
    known = getsource(known_credit_tenant_ids)
    return (
        "seed_from_pending_settlements" in src
        and "seed_from_known_ledgers" in src
        and "*.jsonl" in known
        and "known_settlement_tenant_ids" in known
        and "known_index_tenant_ids" in known
    )


def _tiktok_comment_settles_after_send() -> bool:
    from services.tiktok_business.comment_ai import process_tiktok_comment_ai
    from services.tiktok_business.messaging import _maybe_ai_dm

    src = getsource(process_tiktok_comment_ai)
    dm = getsource(_maybe_ai_dm)
    return (
        "_settle_comment_send" in src
        and "retrying" in src
        and "accepted=True" in src
        and "bind_dm_ids" in dm
        and "accepted=False" in dm
    )


def _legacy_voice_journals_stt() -> bool:
    from handlers.voice_handlers import handle_voice_message

    src = getsource(handle_voice_message)
    return "record_pending_provider" in src and 'category="stt"' in src and "0.006" not in src


def _meta_ai_both_skips_public_after_reply() -> bool:
    from services.meta_comment_brain_send import send_comment_destinations
    from services.meta_comment_replies import process_meta_comment_event

    return "skip_public" in getsource(send_comment_destinations) and "skip_public=already_replied" in getsource(
        process_meta_comment_event
    )


def _meta_public_comment_settles() -> bool:
    from services.meta_comment_brain_send import send_comment_destinations
    from services.meta_comment_replies import process_meta_comment_event

    dest = getsource(send_comment_destinations)
    public = getsource(process_meta_comment_event)
    return (
        dest.index("accepted=False") < dest.index("comment_send_client_missing")
        and "_settle_generated_comment" in public
        and "accepted=True" in public
    )


def _web_chat_indexes_leftover() -> bool:
    from services.omnichannel.deliver import _finish_success
    from services.web_chat.credit_fsm import WebChatCreditHandle
    from services.web_chat.operation_fence import fenced_failure_release
    from services.web_chat.processor_turn_finalize import complete_captured_turn

    src = getsource(WebChatCreditHandle)
    complete = getsource(complete_captured_turn)
    omni = getsource(_finish_success)
    fence = getsource(fenced_failure_release)
    return (
        "_index_open" in src
        and "_index_close" in src
        and "reserve_leftover_reply" not in src
        and "web_inbound_message_id" in complete
        and "_message_settle_ops" in omni
        and "release_web_chat_message_hold" in fence
    )


def _meta_ai_dm_reaches_brain() -> bool:
    from services.meta_comment_replies import process_meta_comment_event

    src = getsource(process_meta_comment_event)
    return (
        "is_static_comment_dm" in src
        and "allows_private_after_public_reply" in src
        and "comment_rule_dm_template_required" not in src
    )


def _stale_leftover_unresolved() -> bool:
    from services.membership.reservation_reconcile import watch_stale_legacy_credits

    src = getsource(watch_stale_legacy_credits)
    return "unresolved" in src and "credit_ledger_service.release" not in src and "release_leftover_reply" not in src


def _stored_history_ok() -> bool:
    reset_conversation_store_for_tests()
    try:
        append_visible_history("eval", "ig-thread-store", [{"id": "m1", "role": "user", "text": "hi"}])
        rows = load_stored_history_rows("eval", "ig-thread-store")
        return bool(rows and rows[0].get("text") == "hi")
    finally:
        reset_conversation_store_for_tests()


def run_contract_cases() -> dict[str, Any]:
    faq = classify_result(
        _turn(),
        TurnResult(stop_reason="ok", extra={"path": "faq_exact"}),
    )
    semantic = classify_result(
        _turn(),
        TurnResult(stop_reason="ok", extra={"path": "faq_semantic"}),
    )
    mixed = classify_result(
        _turn(),
        TurnResult(
            stop_reason="ok",
            ai_called=True,
            extra={"faq_used": True},
            envelope=FinalReplyEnvelope(
                decision="reply",
                messages=[OutboundMessage(destination="dm", text="hi")],
            ),
        ),
    )
    generated = classify_result(
        _turn(),
        TurnResult(
            stop_reason="ok",
            ai_called=True,
            envelope=FinalReplyEnvelope(
                decision="reply",
                messages=[OutboundMessage(destination="dm", text="hi")],
            ),
        ),
    )
    comment_static = classify_result(
        _turn(invocation_kind="comment", surface="comment"),
        TurnResult(
            stop_reason="ok",
            extra={"path": "comment_rule", "comment_mode": "static_comment"},
            envelope=FinalReplyEnvelope(
                decision="deterministic",
                messages=[OutboundMessage(destination="comment", text="Thanks")],
            ),
        ),
    )
    comment_ai = classify_result(
        _turn(invocation_kind="comment", surface="comment"),
        TurnResult(
            stop_reason="ok",
            ai_called=True,
            extra={"comment_mode": "ai_both", "phase": "generate"},
            envelope=FinalReplyEnvelope(
                decision="reply",
                messages=[
                    OutboundMessage(destination="dm", text="Hello"),
                    OutboundMessage(destination="comment", text="Sent you a DM."),
                ],
            ),
        ),
    )
    visual = visual_retrieval_decision(
        has_authorized_asset_id=False,
        requires_visual_reading=True,
        image_analysis_enabled=False,
    )
    empty_history = build_history_snapshot([])
    comment_greet = evaluate_greeting(
        tenant_id="eval",
        message="hi",
        history=empty_history,
        invocation_kind="comment",
    )
    follow_greet = evaluate_greeting(
        tenant_id="eval",
        message="hi",
        history=empty_history,
        invocation_kind="followup",
    )
    flags = channel_flags_for_plan("lite")
    starter = channel_flags_for_plan("starter")
    growth = channel_flags_for_plan("growth")
    free_faq, _ = faq_limits_for_plan("free")
    cases = [
        {"id": "faq_exact_zero", "ok": faq == "faq_only" and message_units_for(faq) == 0},
        {"id": "faq_semantic_zero", "ok": semantic == "faq_only" and message_units_for(semantic) == 0},
        {"id": "mixed_faq_ai_one", "ok": mixed == "mixed_faq_ai" and message_units_for(mixed) == 1},
        {"id": "generated_ai_one", "ok": generated == "generated_ai" and message_units_for(generated) == 1},
        {"id": "comment_static_zero", "ok": comment_static == "static" and message_units_for(comment_static) == 0},
        {"id": "comment_ai_bundle_one", "ok": comment_ai == "generated_ai" and message_units_for(comment_ai) == 1},
        {"id": "visual_disabled", "ok": visual.reason == "disabled"},
        {"id": "lite_comments_locked", "ok": comments_allowed_for_plan("lite") is False},
        {"id": "lite_whatsapp_locked", "ok": flags.get("whatsapp") is False},
        {"id": "lite_web_locked", "ok": flags.get("web") is False},
        {"id": "lite_tiktok_locked", "ok": flags.get("tiktok") is False},
        {"id": "lite_faq_unlocked", "ok": flags.get("faq_enabled") is True},
        {"id": "free_faq_locked", "ok": free_faq is False},
        {"id": "starter_comments_unlocked", "ok": comments_allowed_for_plan("starter") is True},
        {"id": "growth_tiktok_unlocked", "ok": growth.get("tiktok") is True},
        {"id": "starter_web_unlocked", "ok": starter.get("web") is True},
        {"id": "activation_flags_off", "ok": activation_flags_report({}).get("ok") is True},
        {"id": "comment_no_greeting", "ok": comment_greet.eligible is False},
        {"id": "followup_no_greeting", "ok": follow_greet.eligible is False},
        {
            "id": "restricted_has_refuse",
            "ok": refuse_text(RestrictedTopic(id="x", refuse_template="No."), "hi") == "No.",
        },
        {"id": "yes_confirms_request", "ok": looks_like_confirmation("yes") is True},
        {
            "id": "yes_revision_bound",
            "ok": confirmation_valid(
                message_id="m1",
                customer_text="yes",
                expected_revision="1",
                current_revision="1",
            )
            is True,
        },
        {
            "id": "web_conversation_session",
            "ok": session_id_from_conversation("web:tenant:visitor_session_1") == "visitor_session_1",
        },
        {
            "id": "tiktok_conversation_id",
            "ok": provider_conversation_id("shop:tiktok:ttconv_12345678") == "ttconv_12345678",
        },
        {
            "id": "omni_conversation_id",
            "ok": conversation_id_for_brain(
                payload={"conversation_id": "ig-thread-12345678"}
            )
            == "ig-thread-12345678",
        },
        {
            "id": "stored_history_fallback",
            "ok": _stored_history_ok(),
        },
        {
            "id": "meta_inbound_message_id",
            "ok": message_id_for_brain({"_combine_mid": "mid-ig"}) == "mid-ig",
        },
        {
            "id": "whatsapp_inbound_message_id",
            "ok": message_id_for_brain({"provider_message_id": "wamid.abc"}) == "wamid.abc",
        },
        {
            "id": "web_inbound_message_id",
            "ok": web_inbound_message_id("web:t:v", "hi").startswith("user:web:t:v:"),
        },
        {
            "id": "web_request_source",
            "ok": request_source_channel("web_chat") == "web_chat",
        },
        {
            "id": "web_alias_request_source",
            "ok": request_source_channel("web") == "web_chat",
        },
        {
            "id": "tiktok_request_source_rejected",
            "ok": request_source_channel("tiktok") is None,
        },
        {
            "id": "preview_turn_not_billable",
            "ok": owner_preview_turn(_turn(conversation_id="preview:eval")) is True,
        },
        {
            "id": "planner_negates_booking",
            "ok": "service_request" not in {task.type for task in plan_message("Don't book, just asking").tasks},
        },
        {
            "id": "planner_correction",
            "ok": any(task.type == "draft_correction" for task in plan_message("I meant the facial").tasks),
        },
        {
            "id": "safety_blocked_media",
            "ok": evaluate_gates(
                _turn(media=MediaView(safety_blocked=True)),
                apply_credits=False,
                message="photo?",
            ).reason
            == "policy_suppressed",
        },
        {
            "id": "file_extract_in_task_text",
            "ok": "menu.pdf" in inbound_task_text(_turn(media=MediaView(extract_preview="menu.pdf hours")), ""),
        },
        {
            "id": "generate_persists_without_capture",
            "ok": _generate_holds_until_send(),
        },
        {
            "id": "stale_leftover_not_refunded",
            "ok": _stale_leftover_unresolved(),
        },
        {
            "id": "cloud_inbound_hydrates_before_generate",
            "ok": _cloud_inbound_hydrates(),
        },
        {
            "id": "tiktok_media_reaches_brain",
            "ok": _tiktok_media_reaches_brain(),
        },
        {
            "id": "meta_ai_dm_reaches_brain",
            "ok": _meta_ai_dm_reaches_brain(),
        },
        {
            "id": "history_routes_by_channel",
            "ok": _history_routes_by_channel(),
        },
        {
            "id": "comment_threads_share_fallback",
            "ok": _comment_threads_share_fallback(),
        },
        {
            "id": "omni_generate_releases_unsent",
            "ok": _omni_generate_releases_unsent(),
        },
        {
            "id": "web_chat_indexes_leftover",
            "ok": _web_chat_indexes_leftover(),
        },
        {
            "id": "legacy_photo_fetches_ssrf_safe",
            "ok": _legacy_photo_fetches_ssrf_safe(),
        },
        {
            "id": "index_seeds_from_pending",
            "ok": _index_seeds_from_pending(),
        },
        {
            "id": "meta_ai_both_skips_public_after_reply",
            "ok": _meta_ai_both_skips_public_after_reply(),
        },
        {
            "id": "tiktok_comment_settles_after_send",
            "ok": _tiktok_comment_settles_after_send(),
        },
        {
            "id": "legacy_voice_journals_stt",
            "ok": _legacy_voice_journals_stt(),
        },
        {
            "id": "meta_public_comment_settles",
            "ok": _meta_public_comment_settles(),
        },
    ]
    return {
        "ok": all(item["ok"] for item in cases),
        "live_spend": False,
        "case_count": len(cases),
        "cases": cases,
    }
