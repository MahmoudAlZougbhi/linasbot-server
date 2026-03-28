# handlers/text_handlers_delayed.py
# Handles delayed message processing (message combining)

from typing import Optional

from handlers.text_handlers_firestore import *
from handlers.text_handlers_respond import _process_and_respond


async def _delayed_process_messages(
    user_id: str,
    user_data: dict,
    send_message_func,
    send_action_func,
    combine_delay_seconds: Optional[float] = None,
):
    """
    Delays processing to combine rapid messages from the same user.
    combine_delay_seconds: if set (e.g. 0 for dashboard tests), overrides MESSAGE_COMBINING_DELAY.
    """
    try:
        await send_action_func(user_id)  # Send typing indicator
        delay = (
            config.MESSAGE_COMBINING_DELAY
            if combine_delay_seconds is None
            else float(combine_delay_seconds)
        )
        if delay > 0:
            await asyncio.sleep(delay)

        if config.user_pending_messages[user_id]:
            combined_message = " ".join(config.user_pending_messages[user_id])
            config.user_pending_messages[user_id].clear()

            await _process_and_respond(
                user_id, 
                user_name=config.user_names.get(user_id, "عميل"),
                user_input_to_process=combined_message,
                user_data=user_data,
                send_message_func=send_message_func,
                send_action_func=send_action_func
            )
            config.user_last_bot_response_time[user_id] = datetime.datetime.now()
        else:
            pass  # Queue was empty

    except asyncio.CancelledError:
        raise
    except Exception as e:
        print(f"[_delayed_process_messages] ERROR: An error occurred in delayed processing for user {user_id}: {e}")
        import traceback
        traceback.print_exc()
        # When user is in waiting queue and an error occurs, send friendly waiting message instead of "No response captured"
        try:
            db = get_firestore_db()
            current_conversation_id = user_data.get('current_conversation_id')
            if db and current_conversation_id:
                canonical_user_id, _ = get_canonical_user_id_and_phone(user_id, user_data.get("phone_number"))
                app_id_for_firestore = "linas-ai-bot-backend"
                users_coll = db.collection("artifacts").document(app_id_for_firestore).collection("users")
                conv_doc_ref = users_coll.document(canonical_user_id).collection(config.FIRESTORE_CONVERSATIONS_COLLECTION).document(current_conversation_id)
                doc_snap = await asyncio.to_thread(conv_doc_ref.get)
                if not doc_snap.exists and canonical_user_id and (
                    canonical_user_id.startswith("+") or (canonical_user_id.isdigit() and len(canonical_user_id) >= 10)
                ):
                    alt_user_id = canonical_user_id[1:] if canonical_user_id.startswith("+") else f"+{canonical_user_id}"
                    alt_ref = users_coll.document(alt_user_id).collection(config.FIRESTORE_CONVERSATIONS_COLLECTION).document(current_conversation_id)
                    alt_snap = await asyncio.to_thread(alt_ref.get)
                    if alt_snap.exists:
                        doc_snap = alt_snap
                if doc_snap.exists:
                    conv_data = doc_snap.to_dict()
                    human_takeover_active = conv_data.get('human_takeover_active', False)
                    operator_id = conv_data.get('operator_id')
                    if human_takeover_active and not operator_id:
                        user_lang = user_data.get('user_preferred_lang', 'ar')
                        waiting_messages = {
                            "ar": "شوي، منكون معك، شكراً لصبركم، عندنا شوي ضغط 🙏",
                            "en": "Just a moment, we'll be with you shortly. Thank you for your patience 🙏",
                            "fr": "Un instant, nous serons avec vous sous peu. Merci pour votre patience 🙏"
                        }
                        waiting_msg = waiting_messages.get(user_lang, waiting_messages['ar'])
                        await send_message_func(user_id, waiting_msg)
                        user_name = config.user_names.get(user_id, "عميل")
                        await save_conversation_message_to_firestore(
                            user_id, "ai", waiting_msg, current_conversation_id,
                            user_name, user_data.get('phone_number')
                        )
                        print(f"[_delayed_process_messages] Sent waiting message after error (user in queue)")
        except Exception as fallback_err:
            print(f"[_delayed_process_messages] Could not send waiting fallback: {fallback_err}")
