from __future__ import annotations

from typing import Any

from services.live_chat_service_common import (
    _build_operator_idempotency_fingerprint,
    _release_operator_idempotency_lock,
    _try_acquire_operator_send_idempotency,
)


class LiveChatOperatorMixin:
    """Operator send/status and Qiscus/WhatsApp media delivery."""

    APP_ID: Any
    operator_status: Any

    async def send_operator_message(
        self,
        conversation_id: str,
        user_id: str,
        message: str,
        operator_id: str,
        adapter: Any,
        message_type: str = "text",
        idempotency_key: str | None = None,
        tenant_id: str | None = None,
        operator_name: str | None = None,
        request_id: str | None = None,
        source_channel: str | None = None,
    ) -> dict[str, Any]:
        """Send message from operator to customer

        Args:
            conversation_id: The conversation ID
            user_id: The customer's user ID (room_id for Qiscus)
            message: Message content (text for text, base64 for voice/image)
            operator_id: The operator's ID
            adapter: WhatsApp adapter instance
            message_type: Type of message - "text", "voice", or "image"
            idempotency_key:  client key; duplicates within TTL are no-oped (no second WhatsApp delivery).
            tenant_id: Session tenant — used for WA Cloud epoch pause + Requests audit
            request_id: Optional Customer Request id for manual-mode audit linkage
            source_channel: Optional Requests source_channel hint
        """
        lock_ref = None
        completed_ok = False
        db = None
        try:
            from utils.utils import (
                get_canonical_user_id_and_phone,
                get_firestore_db,
                save_conversation_message_to_firestore,
            )

            fingerprint = _build_operator_idempotency_fingerprint(
                idempotency_key,
                conversation_id,
                operator_id,
                message_type,
                message,
            )
            db = get_firestore_db()
            acquired, lock_ref = await _try_acquire_operator_send_idempotency(db, self.APP_ID, fingerprint)
            if not acquired:
                return {
                    "success": True,
                    "message": "Already processed (duplicate request)",
                    "deduplicated": True,
                }

            from services.live_chat_operator_social_delivery import (
                deliver_social_operator_text,
                is_social_live_chat_user,
            )

            if is_social_live_chat_user(user_id) and message_type not in {"text", "voice", "image"}:
                return {
                    "success": False,
                    "error": "Unsupported message type for social Live Chat",
                }

            # Server-authoritative: pause AI before outbound so in-flight AI cannot win the race.
            manual_meta: dict[str, Any] = {}
            try:
                from db.session import WhatsAppDatabaseUnavailable, whatsapp_session
                from services.requests.manual_mode import activate_manual_mode

                wa_session = None
                wa_cm = None
                try:
                    if tenant_id:
                        wa_cm = whatsapp_session()
                        wa_session = wa_cm.__enter__()
                except WhatsAppDatabaseUnavailable:
                    wa_session = None
                try:
                    pause_result = await activate_manual_mode(
                        conversation_id=conversation_id,
                        user_id=user_id,
                        actor_user_id=operator_id,
                        tenant_id=tenant_id,
                        operator_name=operator_name,
                        request_id=request_id,
                        source_channel=source_channel,
                        session=wa_session,
                    )
                    if wa_session is not None:
                        wa_session.commit()
                    manual_meta = {
                        "manual_mode_activated": pause_result.activated,
                        "manual_mode_already_active": pause_result.already_active,
                        "control_epoch": pause_result.control_epoch,
                    }
                finally:
                    if wa_cm is not None:
                        wa_cm.__exit__(None, None, None)
            except Exception as pause_err:
                print(f"⚠️ manual_mode pause before send failed: {pause_err}")
                return {"success": False, "error": f"Failed to pause AI before send: {pause_err}"}

            canonical_user_id, normalized_phone = get_canonical_user_id_and_phone(user_id)
            # For Qiscus, we need to fetch the phone_number from Firebase
            phone_number = None
            if db:
                try:
                    app_id = "linas-ai-bot-backend"
                    user_doc = (
                        db.collection("artifacts")
                        .document(app_id)
                        .collection("users")
                        .document(canonical_user_id)
                        .get()
                    )
                    if user_doc.exists:
                        user_data = user_doc.to_dict()
                        phone_number = user_data.get("phone_full")
                        print(
                            f"📱 Found phone_number from Firebase: ***{str(phone_number)[-4:] if phone_number else ''}"
                        )
                except Exception as e:
                    print(f"⚠️ Could not fetch phone_number from Firebase: {e}")

            # Handle different message types
            if message_type == "voice":
                from services.live_chat_operator_media_handlers import send_operator_voice_message

                result = await send_operator_voice_message(
                    message=message,
                    user_id=user_id,
                    canonical_user_id=canonical_user_id,
                    conversation_id=conversation_id,
                    operator_id=operator_id,
                    phone_number=phone_number,
                    tenant_id=tenant_id,
                    adapter=adapter,
                    manual_meta=manual_meta,
                )
                completed_ok = bool(result.get("success"))
                return result

            elif message_type == "image":
                from services.live_chat_operator_media_handlers import send_operator_image_message

                result = await send_operator_image_message(
                    message=message,
                    user_id=user_id,
                    canonical_user_id=canonical_user_id,
                    conversation_id=conversation_id,
                    operator_id=operator_id,
                    phone_number=phone_number,
                    tenant_id=tenant_id,
                    adapter=adapter,
                    manual_meta=manual_meta,
                )
                completed_ok = bool(result.get("success"))
                return result

            else:  # Default to text
                # Save to Firestore first (SSE broadcasts immediately → message appears in UI fast)
                await save_conversation_message_to_firestore(
                    user_id=canonical_user_id,
                    role="operator",
                    text=message,
                    conversation_id=conversation_id,
                    phone_number=phone_number,  # NOW PASSING PHONE_NUMBER
                    metadata={"operator_id": operator_id, "handled_by": "human"},
                )
                print("✅ Saved operator message to Firestore")

                if is_social_live_chat_user(user_id):
                    delivery = await deliver_social_operator_text(
                        tenant_id=tenant_id,
                        user_id=user_id,
                        conversation_id=conversation_id,
                        text=message,
                    )
                    if delivery and not delivery.get("success"):
                        err = str(delivery.get("error") or "social_delivery_failed")
                        print(f"⚠️ Social operator send failed after save: {err}")
                        return {
                            "success": False,
                            "error": f"Message saved locally but delivery failed: {err}",
                            "delivered": False,
                            **manual_meta,
                        }
                    completed_ok = True
                    return {
                        "success": True,
                        "message": "Message sent successfully",
                        "delivered": True,
                        **manual_meta,
                        **(delivery or {}),
                    }

                # Await WhatsApp send (single delivery; avoids duplicate background tasks)
                try:
                    result = await adapter.send_text_message(canonical_user_id, message)
                    if not isinstance(result, dict) or not result.get("success"):
                        err: str = (
                            str((result or {}).get("error") or "send failed")
                            if isinstance(result, dict)
                            else "send failed"
                        )
                        print(f"⚠️ WhatsApp send failed after save: {err}")
                        return {
                            "success": False,
                            "error": f"Message saved locally but delivery failed: {err}",
                            "delivered": False,
                        }
                    print(f"✅ Operator {operator_id} sent message to ...{str(user_id)[-4:]} via WhatsApp")
                except Exception as send_error:
                    print(f"⚠️ WhatsApp adapter error after save: {send_error}")
                    return {
                        "success": False,
                        "error": f"Message saved locally but delivery failed: {send_error}",
                        "delivered": False,
                    }

                completed_ok = True
                return {
                    "success": True,
                    "message": "Message sent successfully",
                    "delivered": True,
                    **manual_meta,
                }

        except Exception as e:
            print(f"❌ Error sending operator message: {e}")
            import traceback

            traceback.print_exc()
            return {"success": False, "error": str(e)}
        finally:
            if lock_ref is not None and not completed_ok:
                await _release_operator_idempotency_lock(db, lock_ref)

    async def resume_ai_conversation(
        self,
        conversation_id: str,
        user_id: str,
        operator_id: str,
        tenant_id: str | None = None,
        request_id: str | None = None,
        source_channel: str | None = None,
    ) -> dict[str, Any]:
        """Explicit Resume AI — clears server pause (Firestore + WA Cloud epoch)."""
        try:
            from db.session import WhatsAppDatabaseUnavailable, whatsapp_session
            from services.requests.manual_mode import resume_manual_mode

            wa_cm = None
            wa_session = None
            try:
                if tenant_id:
                    wa_cm = whatsapp_session()
                    wa_session = wa_cm.__enter__()
            except WhatsAppDatabaseUnavailable:
                wa_session = None
            try:
                result = await resume_manual_mode(
                    conversation_id=conversation_id,
                    user_id=user_id,
                    actor_user_id=operator_id,
                    tenant_id=tenant_id,
                    request_id=request_id,
                    source_channel=source_channel,
                    session=wa_session,
                )
                if wa_session is not None:
                    wa_session.commit()
            finally:
                if wa_cm is not None:
                    wa_cm.__exit__(None, None, None)

            # Best-effort Live Chat index / canonical state refresh.
            # release_conversation lives on LiveChatLifecycleMixin (composed on LiveChatService).
            release_fn = getattr(self, "release_conversation", None)
            if callable(release_fn):
                release = await release_fn(conversation_id, user_id)
            else:
                release = {"success": False, "error": "release_conversation unavailable"}
            return {
                "success": True,
                "message": "AI resumed for conversation",
                "conversation_id": conversation_id,
                "control_epoch": result.control_epoch,
                "already_active": result.already_active,
                "audit_recorded": result.audit_recorded,
                "release_ok": bool(release.get("success")),
            }
        except Exception as e:
            print(f"❌ Error resuming AI: {e}")
            return {"success": False, "error": str(e)}

    async def update_operator_status(self, operator_id: str, status: str) -> dict[str, Any]:
        """Update operator availability"""
        try:
            valid_statuses = ["available", "busy", "away"]
            if status not in valid_statuses:
                return {"success": False, "error": f"Invalid status. Must be one of: {valid_statuses}"}

            self.operator_status[operator_id] = status
            print(f"✅ Operator {operator_id} status: {status}")

            return {"success": True, "operator_id": operator_id, "status": status}

        except Exception as e:
            return {"success": False, "error": str(e)}
