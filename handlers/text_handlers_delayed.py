from __future__ import annotations

# handlers/text_handlers_delayed.py
# Handles delayed message processing (message combining)
import asyncio
import datetime
import hashlib
import uuid
from typing import Any

import config
from handlers.text_handlers_respond import _process_and_respond
from services.outbound_turn_idempotency import stable_ai_claim_identity, try_claim_ai_turn
from utils.utils import (
    get_canonical_user_id_and_phone,
    get_firestore_db,
    save_conversation_message_to_firestore,
)


async def _delayed_process_messages(
    user_id: str,
    user_data: dict,
    send_message_func: Any,
    send_action_func: Any,
    combine_delay_seconds: float | None = None,
    text_turn_epoch: int | None = None,
) -> Any:
    """
    Delays processing to combine rapid messages from the same user.
    combine_delay_seconds: if set (e.g. 0 for dashboard tests), overrides MESSAGE_COMBINING_DELAY.
    text_turn_epoch: incremented in handle_message per schedule wave; stale tasks must not send.
    """
    try:
        user_data["_ai_turn_trace_id"] = str(user_data.get("_linas_trace_id") or uuid.uuid4())
        trace = user_data["_ai_turn_trace_id"]

        _raw_send = send_message_func

        async def _guarded_send(
            to_number: str,
            message_text: str | None = None,
            image_url: str | None = None,
            audio_url: str | None = None,
        ) -> Any:
            if text_turn_epoch is not None:
                latest = user_data.get("_text_turn_epoch", 0)
                if text_turn_epoch < latest:
                    print(
                        f"⚠️ [text-turn] trace_id={trace} send=STALE_SKIP "
                        f"epoch={text_turn_epoch} latest={latest} user={user_id[:16]}…"
                    )
                    return {"success": True, "skipped_stale_text_turn": True}
            return await _raw_send(
                to_number,
                message_text=message_text,
                image_url=image_url,
                audio_url=audio_url,
            )

        outbound_send = _guarded_send if text_turn_epoch is not None else send_message_func
        from services.ai_reply_delivery import wrap_tracked_send

        outbound_send = wrap_tracked_send(outbound_send, user_data)

        # A typing indicator is cosmetic. Meta (or any other provider) may reject
        # it transiently even while ordinary message delivery remains healthy;
        # never abort the customer reply pipeline for that failure.
        try:
            await send_action_func(user_id)
        except Exception as typing_error:
            channel = str(user_data.get("channel") or "unknown").strip().lower()
            print(f"[typing-indicator] send failed; continuing channel={channel} type={type(typing_error).__name__}")
        delay = config.MESSAGE_COMBINING_DELAY if combine_delay_seconds is None else float(combine_delay_seconds)
        if delay > 0:
            await asyncio.sleep(delay)

        combined_message = None
        from services.scale.message_combine_store import (
            combine_redis_available,
            drain_if_due,
            generation_is_current,
        )

        redis_chunks = None
        if combine_redis_available():
            gen = int(user_data.get("_combine_generation") or 0)
            if gen and not generation_is_current(user_id, gen):
                user_data["_combine_outcome"] = "superseded"
                return
            redis_chunks = drain_if_due(user_id)
            if redis_chunks is None:
                user_data["_combine_outcome"] = "superseded"
                return
            if redis_chunks:
                combined_message = " ".join(
                    str(item.get("text") or "") for item in redis_chunks if str(item.get("text") or "").strip()
                )
                config.user_pending_messages[user_id].clear()
                extra_mids = [str(item.get("mid") or "") for item in redis_chunks if str(item.get("mid") or "")]
                extra_events = [
                    str(item.get("event_id") or "") for item in redis_chunks if str(item.get("event_id") or "")
                ]
                if extra_events:
                    user_data["_combine_event_ids"] = extra_events
                if extra_mids:
                    batch = list(user_data.get("_batch_inbound_mids") or [])
                    for mid in extra_mids:
                        if mid not in batch:
                            batch.append(mid)
                    user_data["_batch_inbound_mids"] = batch

        if combined_message is None:
            if not config.user_pending_messages[user_id]:
                try:
                    from services.scale.conversation_state_redis import get_pending_messages
                    from services.scale.redis_claims import redis_claims_fail_closed

                    remote_pending = get_pending_messages(user_id)
                    if remote_pending:
                        config.user_pending_messages[user_id].extend(remote_pending)
                    elif redis_claims_fail_closed() and remote_pending is None:
                        pass
                except Exception:
                    pass
            if config.user_pending_messages[user_id]:
                combined_message = " ".join(config.user_pending_messages[user_id])
                config.user_pending_messages[user_id].clear()
                try:
                    from services.scale.conversation_state_redis import set_pending_messages

                    set_pending_messages(user_id, [])
                except Exception:
                    pass
                user_data.pop("_dashboard_last_message_for_fallback", None)
                user_data.pop("_dashboard_test_turn_sticky", None)
            elif user_data.get("_dashboard_test_simulation"):
                fb = user_data.pop("_dashboard_last_message_for_fallback", None)
                if fb and str(fb).strip():
                    combined_message = str(fb).strip()
                    print(
                        f"[_delayed_process_messages] INFO: dashboard test fallback (pending queue was empty) "
                        f"user={user_id!r} len={len(combined_message)}"
                    )

        if not combined_message and user_data.get("_dashboard_test_simulation"):
            sticky = user_data.pop("_dashboard_test_turn_sticky", None)
            if sticky and str(sticky).strip():
                combined_message = str(sticky).strip()
                print(
                    f"[_delayed_process_messages] INFO: dashboard sticky turn text recovered "
                    f"user={user_id!r} len={len(combined_message)}"
                )

        if combined_message:
            try:
                mids = user_data.pop("_batch_inbound_mids", []) or []
                bfps = user_data.pop("_batch_turn_body_fps", []) or []
                if not isinstance(mids, list):
                    mids = []
                if not mids:
                    extra_events = [
                        str(item).strip() for item in (user_data.get("_combine_event_ids") or []) if str(item).strip()
                    ]
                    inbound_one = str(user_data.get("_inbound_event_id") or "").strip()
                    mids = extra_events or ([inbound_one] if inbound_one else [])
                claim_id = stable_ai_claim_identity(user_id, user_data.get("phone_number"))
                from services.ai_reply_turn_runtime import (
                    ensure_turn_started,
                    finalize_delivery,
                    pending_delivery_for_claim,
                    reset_turn_runtime_state,
                    retry_saved_reply_delivery,
                    try_reserve_for_ai,
                )
                from services.outbound_turn_idempotency import _claim_key_basis

                key_basis = _claim_key_basis(claim_id, mids, bfps) if (mids or bfps) else ""
                # Conversation state is reused for the same sender. Rotate all
                # logical-turn/delivery evidence before this batch so a prior
                # Meta message_id can never make a later no-send turn look sent.
                reset_turn_runtime_state(user_data)

                pending = pending_delivery_for_claim(key_basis) if key_basis else None
                if pending:
                    user_data["_logical_reply_id"] = str(pending["logical_reply_id"])
                    user_data["_ai_turn_started"] = True
                    delivered = await retry_saved_reply_delivery(
                        user_data=user_data,
                        send_message_func=outbound_send,
                        user_id=user_id,
                        pending=pending,
                    )
                    finalize_delivery({"user_data": user_data})
                    if delivered:
                        print(f"[ai-turn] trace_id={trace} delivery_retry=DELIVERED saved_reply")
                    else:
                        print(f"[ai-turn] trace_id={trace} delivery_retry=FAILED saved_reply")
                    return

                external_turn_id = f"claim:{hashlib.sha256(key_basis.encode()).hexdigest()}" if key_basis else None
                ensure_turn_started(
                    user_data,
                    claim_key_basis=key_basis or None,
                    external_inbound_id=external_turn_id,
                )

                if (mids or bfps) and not await try_claim_ai_turn(
                    claim_id,
                    mids,
                    inbound_body_fps=bfps,
                    binding_id=str(user_data.get("meta_binding_id") or ""),
                    inbound_event_id=str(user_data.get("_inbound_event_id") or ""),
                ):
                    print(
                        f"⚠️ [ai-turn] trace_id={trace} claim=DUPLICATE_SKIP "
                        f"user={user_id[:20]}… mids={len(mids)} bfps={len(bfps)} "
                        f"claim_key={claim_id[:16]}…"
                    )
                    return
                if not try_reserve_for_ai(user_data):
                    print(f"[ai-turn] trace_id={trace} credit=BLOCKED — no customer reply")
                    return
                if mids or bfps:
                    print(
                        f"[ai-turn] trace_id={trace} claim=OK claim_key={claim_id[:20]}… "
                        f"inbound_mids_n={len(mids)} body_fps_n={len(bfps)} "
                        f"combined_len={len(combined_message or '')}"
                    )
                else:
                    print(
                        f"[ai-turn] trace_id={trace} claim=SKIPPED(no_mids_no_bodyfp) "
                        f"combined_len={len(combined_message or '')} — distributed dedupe inactive for this turn"
                    )
                try:
                    import time as _time

                    from services.scale.latency_histogram import observe
                    from services.scale.trace_span import mark

                    mark(str(trace), "ai_started")
                    _ai_t0 = _time.time()
                except Exception:
                    _ai_t0 = None
                await _process_and_respond(
                    user_id,
                    user_name=config.user_names.get(user_id, "عميل"),
                    user_input_to_process=combined_message,
                    user_data=user_data,
                    send_message_func=outbound_send,
                    send_action_func=send_action_func,
                )
                if _ai_t0 is not None:
                    try:
                        mark(str(trace), "ai_finished")
                        observe("ai_ms", max(0.0, (_time.time() - _ai_t0) * 1000.0))
                    except Exception:
                        pass
                delivery_summary = finalize_delivery({"user_data": user_data})
                if delivery_summary.get("delivery") != "delivered" and key_basis:
                    from services.outbound_turn_idempotency import release_ai_turn_claim

                    await release_ai_turn_claim(key_basis)
                elif delivery_summary.get("delivery") == "delivered" and key_basis:
                    from services.outbound_turn_idempotency import complete_ai_turn_claim

                    await complete_ai_turn_claim(key_basis)
            finally:
                user_data.pop("_dashboard_test_turn_sticky", None)
            config.user_last_bot_response_time[user_id] = datetime.datetime.now()
        else:
            print(
                f"[_delayed_process_messages] WARN: pending message queue empty for {user_id!r} "
                f"(no GPT turn). If another request cancelled a delayed task, messages may have been cleared."
            )
            if user_data.get("_dashboard_test_simulation"):
                user_data.pop("_dashboard_test_turn_sticky", None)
                try:
                    user_lang = (user_data.get("user_preferred_lang") or "ar").lower()
                    if user_lang == "en":
                        empty_q_msg = (
                            "No message text reached the processor (pending queue empty). "
                            "Retry once; avoid concurrent tests for the same phone."
                        )
                    elif user_lang == "fr":
                        empty_q_msg = (
                            "Aucun texte n'a atteint le processeur (file d'attente vide). "
                            "Réessayez ; évitez les tests simultanés pour le même numéro."
                        )
                    else:
                        empty_q_msg = (
                            "لم يُعالَج نص الرسالة (طابور الرسائل فاضي). جرّب مرة ثانية وتجنّب طلبين معًا لنفس الرقم."
                        )
                    await outbound_send(user_id, empty_q_msg)
                except Exception as eq_err:
                    print(f"[_delayed_process_messages] Dashboard empty-queue notify failed: {eq_err}")

        from services.scale.conversation_session import persist_from_process

        persist_from_process(user_id)

    except asyncio.CancelledError:
        raise
    except Exception as e:
        print(
            f"[_delayed_process_messages] ERROR: An error occurred in delayed processing for user ...{str(user_id)[-4:]}: {e}"
        )
        import traceback

        traceback.print_exc()
        if user_data.get("_dashboard_test_simulation"):
            _diag = f"{type(e).__name__}: {e}"
            user_data["_dashboard_processing_error"] = _diag if len(_diag) <= 800 else _diag[:797] + "..."
        sent_error_outbound = False
        # When user is in waiting queue and an error occurs, send friendly waiting message instead of "No response captured"
        try:
            db = get_firestore_db()
            current_conversation_id = user_data.get("current_conversation_id")
            if db and current_conversation_id:
                canonical_user_id, _ = get_canonical_user_id_and_phone(user_id, user_data.get("phone_number"))
                app_id_for_firestore = "linas-ai-bot-backend"
                users_coll = db.collection("artifacts").document(app_id_for_firestore).collection("users")
                conv_doc_ref = (
                    users_coll.document(canonical_user_id)
                    .collection(config.FIRESTORE_CONVERSATIONS_COLLECTION)
                    .document(current_conversation_id)
                )
                doc_snap = await asyncio.to_thread(conv_doc_ref.get)
                if (
                    not doc_snap.exists
                    and canonical_user_id
                    and (
                        canonical_user_id.startswith("+")
                        or (canonical_user_id.isdigit() and len(canonical_user_id) >= 10)
                    )
                ):
                    alt_user_id = (
                        canonical_user_id[1:] if canonical_user_id.startswith("+") else f"+{canonical_user_id}"
                    )
                    alt_ref = (
                        users_coll.document(alt_user_id)
                        .collection(config.FIRESTORE_CONVERSATIONS_COLLECTION)
                        .document(current_conversation_id)
                    )
                    alt_snap = await asyncio.to_thread(alt_ref.get)
                    if alt_snap.exists:
                        doc_snap = alt_snap
                if doc_snap.exists:
                    conv_data = doc_snap.to_dict()
                    human_takeover_active = conv_data.get("human_takeover_active", False)
                    operator_id = conv_data.get("operator_id")
                    if human_takeover_active and not operator_id:
                        user_lang = user_data.get("user_preferred_lang", "ar")
                        waiting_messages = {
                            "ar": "شوي، منكون معك، شكراً لصبركم، عندنا شوي ضغط 🙏",
                            "en": "Just a moment, we'll be with you shortly. Thank you for your patience 🙏",
                            "fr": "Un instant, nous serons avec vous sous peu. Merci pour votre patience 🙏",
                        }
                        waiting_msg = waiting_messages.get(user_lang, waiting_messages["ar"])
                        await outbound_send(user_id, waiting_msg)
                        user_name = config.user_names.get(user_id, "عميل")
                        await save_conversation_message_to_firestore(
                            user_id,
                            "ai",
                            waiting_msg,
                            current_conversation_id,
                            user_name,
                            user_data.get("phone_number"),
                        )
                        print("[_delayed_process_messages] Sent waiting message after error (user in queue)")
                        sent_error_outbound = True
        except Exception as fallback_err:
            print(f"[_delayed_process_messages] Could not send waiting fallback: {fallback_err}")

        if not sent_error_outbound and user_data.get("_dashboard_test_simulation"):
            try:
                from services.dynamic_messages_service import get_dynamic_message

                user_lang = user_data.get("user_preferred_lang", "ar")
                err_msg = (
                    get_dynamic_message("generic_error_message", user_lang)
                    or "عذراً، صار خطأ أثناء المعالجة. جرّب مرة ثانية أو راجع سجلات السيرفر."
                )
                await outbound_send(user_id, err_msg)
                print(f"[_delayed_process_messages] Sent generic error for dashboard test after exception: {e!r}")
            except Exception as dash_err:
                print(f"[_delayed_process_messages] Dashboard test error fallback send failed: {dash_err}")
        user_data.pop("_dashboard_test_turn_sticky", None)
        try:
            from services.ai_reply_turn_runtime import on_ai_failed

            on_ai_failed({"user_data": user_data})
        except Exception:
            pass
        try:
            from services.outbound_turn_idempotency import _claim_key_basis, release_ai_turn_claim

            mids = user_data.get("_batch_inbound_mids") or []
            bfps = user_data.get("_batch_turn_body_fps") or []
            if mids or bfps:
                claim_id = stable_ai_claim_identity(user_id, user_data.get("phone_number"))
                key_basis = _claim_key_basis(claim_id, mids, bfps)
                if key_basis:
                    await release_ai_turn_claim(key_basis)
        except Exception:
            pass
        raise
