from __future__ import annotations

# handlers/text_handlers_delayed.py
# Handles delayed message processing (message combining)
import asyncio
import datetime
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
        user_data["_ai_turn_trace_id"] = str(uuid.uuid4())
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
        if not config.user_pending_messages[user_id]:
            try:
                from services.scale.conversation_state_redis import get_pending_messages
                from services.scale.redis_claims import redis_claims_fail_closed

                remote_pending = get_pending_messages(user_id)
                if remote_pending:
                    config.user_pending_messages[user_id].extend(remote_pending)
                elif redis_claims_fail_closed() and remote_pending is None:
                    # Do not assume another node has no pending chunks when Redis is down.
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
                claim_id = stable_ai_claim_identity(user_id, user_data.get("phone_number"))
                if (mids or bfps) and not await try_claim_ai_turn(claim_id, mids, inbound_body_fps=bfps):
                    print(
                        f"⚠️ [ai-turn] trace_id={trace} claim=DUPLICATE_SKIP "
                        f"user={user_id[:20]}… mids={len(mids)} bfps={len(bfps)} "
                        f"claim_key={claim_id[:16]}…"
                    )
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
                await _process_and_respond(
                    user_id,
                    user_name=config.user_names.get(user_id, "عميل"),
                    user_input_to_process=combined_message,
                    user_data=user_data,
                    send_message_func=outbound_send,
                    send_action_func=send_action_func,
                )
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
