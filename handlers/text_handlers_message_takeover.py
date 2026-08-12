from __future__ import annotations

# Human-takeover Firestore helpers extracted from handle_message (LOC split).
import asyncio
import datetime
from typing import Any

import config
from services.dynamic_messages_service import get_dynamic_message
from utils.utils import (
    get_canonical_user_id_and_phone,
    notify_human_on_whatsapp,
    save_conversation_message_to_firestore,
)


def build_firestore_user_candidates(canonical_user_id: str, raw_user_id: str) -> list:
    """Build candidate Firestore user IDs to handle legacy/raw identity paths."""
    candidates = []
    for candidate in [canonical_user_id, raw_user_id]:
        if candidate and candidate not in candidates:
            candidates.append(candidate)
        if candidate and (candidate.startswith("+") or (candidate.isdigit() and len(candidate) >= 10)):
            alt_candidate = candidate[1:] if candidate.startswith("+") else f"+{candidate}"
            if alt_candidate not in candidates:
                candidates.append(alt_candidate)
    return candidates


async def resolve_conversation_doc_ref(
    users_coll: Any, conversation_id: str, canonical_user_id: str, raw_user_id: str
) -> Any:
    """
    Resolve conversation doc across canonical/raw/alt user paths.
    Returns (doc_ref, doc_snap, resolved_user_id).
    """
    candidate_user_ids = build_firestore_user_candidates(canonical_user_id, raw_user_id)
    last_ref = None
    last_snap = None

    for candidate_user_id in candidate_user_ids:
        candidate_ref = (
            users_coll.document(candidate_user_id)
            .collection(config.FIRESTORE_CONVERSATIONS_COLLECTION)
            .document(conversation_id)
        )
        candidate_snap = await asyncio.to_thread(candidate_ref.get)
        last_ref = candidate_ref
        last_snap = candidate_snap
        if candidate_snap.exists:
            return candidate_ref, candidate_snap, candidate_user_id

    return last_ref, last_snap, canonical_user_id


async def trigger_human_takeover(
    *,
    db: Any,
    user_id: str,
    user_name: str,
    user_data: dict,
    send_message_func: Any,
    current_conversation_id: Any,
    trigger_source: str,
    escalation_reason: str,
    customer_message: str,
    escalation_score: float | None = None,
    detected_issues: list | None = None,
) -> Any:
    """Mark conversation as waiting_human, notify admins, and write audit event."""
    if not current_conversation_id:
        return
    if not db:
        print("⚠️ _trigger_human_takeover skipped: Firestore not available")
        return

    from utils.utils import (
        conversation_any_path_post_release_blocked,
        merge_conversation_user_id_variants,
        update_conversation_on_all_existing_paths,
    )

    if await conversation_any_path_post_release_blocked(current_conversation_id, user_id):
        print("⚠️ _trigger_human_takeover skipped: post-release cooldown on at least one user path")
        return

    update_payload = {
        "status": "waiting_human",
        "human_takeover_active": True,
        "human_takeover_requested": True,
        "operator_id": None,
        "conversation_state": "waiting_for_operator",
        "escalation_reason": escalation_reason,
        "escalation_time": datetime.datetime.now(),
        "last_updated": datetime.datetime.now(),
        "post_release_escalation_suppressed_until": None,
    }
    if escalation_score is not None:
        update_payload["escalation_score"] = escalation_score
    if detected_issues:
        update_payload["detected_issues"] = detected_issues

    try:
        n = await update_conversation_on_all_existing_paths(current_conversation_id, user_id, update_payload)
        if n == 0:
            print(f"⚠️ Conversation {current_conversation_id} not found in Firestore on any user path")
            return
        print(f"✅ Conversation marked as waiting_human in Firebase ({n} doc path(s))")
        try:
            canonical_user_id, _ = get_canonical_user_id_and_phone(user_id, user_data.get("phone_number"))
            from services.live_chat_service import live_chat_service

            live_chat_service.invalidate_cache()
            asyncio.create_task(
                live_chat_service._refresh_index_for_conversation(canonical_user_id, current_conversation_id)
            )
        except Exception as idx_err:
            print(f"⚠️ Index refresh after handover: {idx_err}")
    except Exception as e:
        print(f"⚠️ Failed to mark conversation as waiting_human: {e}")
        return

    for vid in merge_conversation_user_id_variants("", user_id):
        config.user_in_human_takeover_mode[vid] = True

    escalation_messages = {
        "ar": "تم تحويلك لأحد من موظفينا شوي، ويكون معك. شكراً لصبرك 🙏",
        "en": "Thanks for your patience. You'll be transferred to one of our staff members shortly. 🙏",
        "fr": "Merci pour votre patience. Vous serez transféré à l'un de nos employés sous peu. 🙏",
    }
    calm_handover_messages = {
        "ar": "أسف/ة إنك مش راضي/ة، رح حوّلك عند واحد من موظفينا يتواصل معك 🙏",
        "en": "Sorry you're not satisfied. I'll transfer you to one of our staff to connect with you 🙏",
        "fr": "Désolé que vous ne soyez pas satisfait. Je vous transfère à un de nos employés 🙏",
    }
    issues = set(detected_issues or [])
    should_use_calm_handover = bool(issues.intersection({"offensive_language", "anger_detected"}))
    escalation_msg = escalation_messages.get(user_data.get("user_preferred_lang", "ar"), escalation_messages["ar"])
    if should_use_calm_handover:
        escalation_msg = calm_handover_messages.get(
            user_data.get("user_preferred_lang", "ar"),
            calm_handover_messages["ar"],
        )
    await send_message_func(user_id, escalation_msg)
    await save_conversation_message_to_firestore(
        user_id,
        "ai",
        escalation_msg,
        current_conversation_id,
        user_name,
        user_data.get("phone_number"),
        metadata={"handled_by": "ai", "source": "smart_message", "event": "auto_handover_escalation"},
    )

    notify_human_on_whatsapp(
        user_name,
        config.user_gender.get(user_id, "unknown"),
        customer_message,
        type_of_notification=f"{trigger_source} - {escalation_reason}",
    )

    try:
        from services.human_takeover_notification_service import human_takeover_notification_service

        notify_result = await human_takeover_notification_service.notify_and_audit_handoff(
            user_id=user_id,
            user_gender=config.user_gender.get(user_id, "unknown"),
            customer_name=user_name,
            customer_phone=user_data.get("phone_number", "Unknown"),
            escalation_reason=escalation_reason,
            last_message=customer_message,
            trigger_source=trigger_source,
            conversation_id=current_conversation_id,
            extra_details={"escalation_score": escalation_score, "detected_issues": detected_issues or []},
        )
        notification_result = notify_result.get("notification_result", {})
        if notification_result.get("success"):
            print(f"✅ Sent notifications to {notification_result.get('sent_count')} admin(s)")
        else:
            print(f"⚠️ Notification sending failed: {notification_result.get('error')}")
    except Exception as notify_error:
        print(f"⚠️ Error sending human takeover notifications: {notify_error}")
        import traceback

        traceback.print_exc()


async def maybe_send_takeover_autoreply(
    *,
    db: Any,
    user_id: str,
    user_name: str,
    user_data: dict,
    send_message_func: Any,
) -> bool:
    """Return True if handle_message should stop (operator/waiting auto-reply sent)."""
    # Check Firestore for human takeover status (use canonical path + alternate fallback)
    if db:
        conv_for_takeover_check = user_data.get("current_conversation_id")
        if not conv_for_takeover_check:
            try:
                app_id_for_firestore = "linas-ai-bot-backend"
                canonical_user_id, _ = get_canonical_user_id_and_phone(user_id, user_data.get("phone_number"))
                users_coll = db.collection("artifacts").document(app_id_for_firestore).collection("users")
                from utils.utils import _resolve_latest_conversation_id

                user_doc_ref = users_coll.document(canonical_user_id)
                conversations_collection_for_user = user_doc_ref.collection(config.FIRESTORE_CONVERSATIONS_COLLECTION)
                conv_for_takeover_check = await _resolve_latest_conversation_id(conversations_collection_for_user)
                if conv_for_takeover_check:
                    print(
                        f"[handle_message] INFO: Takeover sync using latest conversation "
                        f"{conv_for_takeover_check} (no current_conversation_id)"
                    )
            except Exception as e:
                print(f"⚠️ Takeover sync: could not resolve conversation: {e}")
                conv_for_takeover_check = None

        if conv_for_takeover_check:
            try:
                app_id_for_firestore = "linas-ai-bot-backend"
                canonical_user_id, _ = get_canonical_user_id_and_phone(user_id, user_data.get("phone_number"))
                users_coll = db.collection("artifacts").document(app_id_for_firestore).collection("users")
                conv_doc_ref, doc_snap, _ = await resolve_conversation_doc_ref(
                    users_coll,
                    conv_for_takeover_check,
                    canonical_user_id,
                    user_id,
                )
                if doc_snap.exists:
                    conv_data = doc_snap.to_dict()
                    from utils.utils import sync_post_release_cooldown_from_conv_payload

                    sync_post_release_cooldown_from_conv_payload(user_data, conv_data)
                    was_in_takeover = config.user_in_human_takeover_mode.get(user_id, False)
                    new_takeover = conv_data.get("human_takeover_active", False)
                    if new_takeover:
                        config.user_in_human_takeover_mode[user_id] = True
                    else:
                        from utils.utils import _clear_takeover_flags_for_user

                        _clear_takeover_flags_for_user(canonical_user_id, user_id, canonical_user_id)
                    if was_in_takeover and not new_takeover:
                        user_data["just_returned_from_human_takeover"] = True
                        from utils.utils import (
                            is_post_takeover_escalation_cooldown,
                            set_post_takeover_escalation_cooldown,
                        )

                        if not is_post_takeover_escalation_cooldown(user_data):
                            set_post_takeover_escalation_cooldown(user_data)
                        print(f"[handle_message] INFO: User ...{str(user_id)[-4:]} just returned from human takeover.")
                    if config.user_in_human_takeover_mode[user_id]:
                        if user_data.get("_dashboard_test_simulation"):
                            print(
                                f"[handle_message] INFO: User {user_id} in takeover queue, but dashboard test "
                                "simulation is on — skipping operator/waiting auto-reply so the AI can respond."
                            )
                        else:
                            operator_id = conv_data.get("operator_id")
                            user_lang = user_data.get("user_preferred_lang", "ar")
                            conv_id_for_save = user_data.get("current_conversation_id") or conv_for_takeover_check

                            if operator_id:
                                # User has an operator — never stay silent.
                                # Send assignment notice once, then send a short reminder on each user turn.
                                print(
                                    f"[handle_message] INFO: User ...{str(user_id)[-4:]} has operator. AI will not respond."
                                )
                                if not user_data.get("notified_human_takeover"):
                                    operator_name = conv_data.get("operator_name")
                                    if not operator_name:
                                        if operator_id and "@" in str(operator_id):
                                            operator_name = (
                                                str(operator_id)
                                                .split("@")[0]
                                                .replace(".", " ")
                                                .replace("_", " ")
                                                .title()
                                            )
                                        else:
                                            operator_name = operator_id
                                    handover_messages = {
                                        "ar": f"📞 تم تحويل المحادثة إلى {operator_name}. سيقوم بالرد عليك قريباً.",
                                        "en": f"📞 The conversation has been transferred to {operator_name}. They will respond to you shortly.",
                                        "fr": f"📞 La conversation a été transférée à {operator_name}. Il vous répondra sous peu.",
                                    }
                                    handover_msg = handover_messages.get(user_lang, handover_messages["ar"])
                                    await send_message_func(user_id, handover_msg)
                                    await save_conversation_message_to_firestore(
                                        user_id,
                                        "ai",
                                        handover_msg,
                                        conv_id_for_save,
                                        user_name,
                                        user_data.get("phone_number"),
                                        metadata={
                                            "handled_by": "ai",
                                            "source": "smart_message",
                                            "event": "operator_assigned_notice",
                                        },
                                    )
                                    user_data["notified_human_takeover"] = True
                                else:
                                    # Operator is handling the chat — do not send a bot follow-up on every user turn
                                    # (it duplicated the human reply and looked like "two messages").
                                    print(
                                        f"[handle_message] INFO: User {user_id} has operator; skipping per-turn bot follow-up."
                                    )
                            else:
                                # User is in waiting queue (no operator yet) — always send "please wait" (every time user speaks)
                                print(
                                    f"[handle_message] INFO: User {user_id} in waiting queue. Sending waiting auto-reply."
                                )
                                waiting_msg = (
                                    get_dynamic_message("waiting_queue_message", user_lang)
                                    or "شوي، منكون معك، شكراً لصبركم، عندنا شوي ضغط 🙏"
                                )
                                await send_message_func(user_id, waiting_msg)
                                await save_conversation_message_to_firestore(
                                    user_id,
                                    "ai",
                                    waiting_msg,
                                    conv_id_for_save,
                                    user_name,
                                    user_data.get("phone_number"),
                                    metadata={
                                        "handled_by": "ai",
                                        "source": "smart_message",
                                        "event": "waiting_queue_autoreply",
                                    },
                                )
                            return True
                else:
                    print(
                        f"WARNING: Conversation {conv_for_takeover_check} not found in Firestore during takeover check."
                    )
            except Exception as e:
                print(f"❌ ERROR checking human takeover status from Firestore for user ...{str(user_id)[-4:]}: {e}")
    return False
