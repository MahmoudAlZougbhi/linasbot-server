"""Empty-queue and exception paths for delayed combine flush."""

from __future__ import annotations

import asyncio
from typing import Any

import config
from services.brain.silence import log_customer_generation_failure
from services.scale.outbound_turn_idempotency import stable_ai_claim_identity
from utils.utils import (
    get_canonical_user_id_and_phone,
    get_firestore_db,
    save_conversation_message_to_firestore,
)


async def notify_empty_dashboard_queue(
    *,
    user_id: str,
    user_data: dict[str, Any],
    outbound_send: Any,
) -> None:
    print(
        f"[_delayed_process_messages] WARN: pending message queue empty for {user_id!r} "
        f"(no GPT turn). If another request cancelled a delayed task, messages may have been cleared."
    )
    if not user_data.get("_dashboard_test_simulation"):
        return
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
            empty_q_msg = "لم يُعالَج نص الرسالة (طابور الرسائل فاضي). جرّب مرة ثانية وتجنّب طلبين معًا لنفس الرقم."
        await outbound_send(user_id, empty_q_msg)
    except Exception as eq_err:
        print(f"[_delayed_process_messages] Dashboard empty-queue notify failed: {eq_err}")


async def handle_delayed_process_exception(
    *,
    exc: BaseException,
    user_id: str,
    user_data: dict[str, Any],
    outbound_send: Any,
) -> None:
    print(
        f"[_delayed_process_messages] ERROR: An error occurred in delayed processing "
        f"for user ...{str(user_id)[-4:]}: {exc}"
    )
    import traceback

    traceback.print_exc()
    if user_data.get("_dashboard_test_simulation"):
        diag = f"{type(exc).__name__}: {exc}"
        user_data["_dashboard_processing_error"] = diag if len(diag) <= 800 else diag[:797] + "..."
    sent_error_outbound = await _maybe_waiting_queue_notice(
        user_id=user_id,
        user_data=user_data,
        outbound_send=outbound_send,
    )
    if not sent_error_outbound:
        log_customer_generation_failure(
            stage="delayed_process_exception",
            extra={"exception_class": type(exc).__name__},
        )
    user_data.pop("_dashboard_test_turn_sticky", None)
    try:
        from services.brain.ai_reply.ai_reply_turn_runtime import on_ai_failed

        on_ai_failed({"user_data": user_data})
    except Exception:
        pass
    try:
        from services.scale.outbound_turn_idempotency import _claim_key_basis, release_ai_turn_claim

        mids = user_data.get("_batch_inbound_mids") or []
        bfps = user_data.get("_batch_turn_body_fps") or []
        if mids or bfps:
            claim_id = stable_ai_claim_identity(user_id, user_data.get("phone_number"))
            key_basis = _claim_key_basis(claim_id, mids, bfps)
            if key_basis:
                await release_ai_turn_claim(key_basis)
    except Exception:
        pass


async def _maybe_waiting_queue_notice(
    *,
    user_id: str,
    user_data: dict[str, Any],
    outbound_send: Any,
) -> bool:
    try:
        db = get_firestore_db()
        current_conversation_id = user_data.get("current_conversation_id")
        if not db or not current_conversation_id:
            return False
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
            and (canonical_user_id.startswith("+") or (canonical_user_id.isdigit() and len(canonical_user_id) >= 10))
        ):
            alt_user_id = canonical_user_id[1:] if canonical_user_id.startswith("+") else f"+{canonical_user_id}"
            alt_ref = (
                users_coll.document(alt_user_id)
                .collection(config.FIRESTORE_CONVERSATIONS_COLLECTION)
                .document(current_conversation_id)
            )
            alt_snap = await asyncio.to_thread(alt_ref.get)
            if alt_snap.exists:
                doc_snap = alt_snap
        if not doc_snap.exists:
            return False
        conv_data = doc_snap.to_dict() or {}
        if not (conv_data.get("human_takeover_active") and not conv_data.get("operator_id")):
            return False
        from services.owner_copilot.dynamic_messages_service import get_dynamic_message

        user_lang = user_data.get("user_preferred_lang", "ar")
        waiting_msg = (get_dynamic_message("waiting_queue_message", user_lang) or "").strip()
        if not waiting_msg:
            log_customer_generation_failure(stage="delayed_error_takeover_queue")
            return False
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
        return True
    except Exception as fallback_err:
        print(f"[_delayed_process_messages] Could not send waiting fallback: {fallback_err}")
        return False
