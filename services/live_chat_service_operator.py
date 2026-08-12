from __future__ import annotations

from typing import Any

from services.live_chat_service_common import (
    _build_operator_idempotency_fingerprint,
    _release_operator_idempotency_lock,
    _try_acquire_operator_send_idempotency,
)
from services.media_service import build_whatsapp_audio_delivery_url


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
                # message contains base64 audio data

                print(f"🎙️ Operator {operator_id} recorded voice message for ...{str(user_id)[-4:]}")

                # Step 0: Convert WebM to Opus (Qiscus/WhatsApp standard)
                print("� Converting voice to Opus format (WhatsApp standard)...")
                audio_data_to_upload = message
                upload_file_name = f"voice_{user_id}_{int(__import__('time').time())}.webm"
                upload_file_type = "audio/webm"

                try:
                    from utils.utils import convert_webm_to_opus

                    opus_data, opus_file_name = convert_webm_to_opus(message)
                    if opus_file_name:  # Conversion successful
                        audio_data_to_upload = opus_data
                        upload_file_name = opus_file_name
                        upload_file_type = "audio/ogg"
                        print("✅ Voice converted to OGG/Opus")
                except Exception as e:
                    print(f"⚠️ WebM to Opus conversion failed: {e}")
                    print("   Continuing with original WebM format...")

                # Step 1: Upload to Firebase Storage
                storage_url = None
                try:
                    from utils.utils import upload_base64_to_firebase_storage

                    storage_url = await upload_base64_to_firebase_storage(
                        base64_data=audio_data_to_upload, file_name=upload_file_name, file_type=upload_file_type
                    )
                    print(f"✅ Voice uploaded to Storage: {storage_url}")
                except Exception as e:
                    print(f"⚠️ Failed to upload to Storage: {e}")
                    if "404" in str(e) and "bucket does not exist" in str(e).lower():
                        print("   📌 HINT: Check storageBucket in data/firebase_data.json")
                        print("   📌 Actual bucket: linas-ai-bot.firebasestorage.app (not appspot.com)")
                    storage_url = None

                # Step 2: Save to Firebase Firestore
                print("📝 Saving voice metadata to Firebase Firestore...")
                await save_conversation_message_to_firestore(
                    user_id=canonical_user_id,
                    role="operator",
                    text="[Voice Message from Operator]",
                    conversation_id=conversation_id,
                    phone_number=phone_number,  # NOW PASSING PHONE_NUMBER
                    metadata={
                        "operator_id": operator_id,
                        "handled_by": "human",
                        "type": "voice",
                        "audio_url": storage_url,  # Store the public URL with key name 'audio_url' for easy retrieval
                        "audio_mime_type": upload_file_type,
                        "message_length": len(message),
                    },
                )

                # Step 3: Send voice message via WhatsApp
                print(f"🎙️ Sending voice message via WhatsApp to ...{str(user_id)[-4:]}...")
                try:
                    if storage_url:
                        whatsapp_audio_url = build_whatsapp_audio_delivery_url(storage_url)
                        print(f"📤 Proxy URL for WhatsApp: {whatsapp_audio_url}")
                        send_result = await adapter.send_audio_message(canonical_user_id, whatsapp_audio_url)
                        if send_result.get("success"):
                            print("✅ Sent voice message via WhatsApp")
                        else:
                            error_msg = send_result.get("error", "Unknown error")
                            print(f"⚠️ WhatsApp audio send failed: {error_msg}")
                            print(f"⚠️ Audio URL was: {storage_url}")
                            return {
                                "success": False,
                                "error": f"WhatsApp audio send failed: {error_msg}",
                                "storage_url": storage_url,
                                "whatsapp_audio_url": whatsapp_audio_url,
                            }
                    else:
                        # Fallback: send text notification if storage upload failed
                        text_notification = "تم استلام رسالة صوتية من المشغل. يرجى فتح لوحة المعلومات لسماعها."
                        await adapter.send_text_message(canonical_user_id, text_notification)
                        print("✅ Sent text notification (storage upload failed)")
                except Exception as e:
                    print(f"⚠️ Failed to send via WhatsApp: {e}")
                    import traceback

                    traceback.print_exc()
                    return {"success": False, "error": f"Failed to send voice: {str(e)}"}

                print(f"✅ Voice message processed and sent for ...{str(user_id)[-4:]}")

                completed_ok = True
                return {
                    "success": True,
                    "message": "Voice message sent successfully",
                    "storage_url": storage_url,
                    "whatsapp_audio_url": build_whatsapp_audio_delivery_url(storage_url) if storage_url else None,
                    **manual_meta,
                }

            elif message_type == "image":
                # message contains base64 image data
                print(f"🖼️ Operator {operator_id} uploaded image for ...{str(user_id)[-4:]}")
                print("📝 Uploading image to Firebase Storage...")

                # Step 1: Upload to Firebase Storage
                storage_url = None
                try:
                    from utils.utils import upload_base64_to_firebase_storage

                    storage_url = await upload_base64_to_firebase_storage(
                        base64_data=message,
                        file_name=f"image_{user_id}_{int(__import__('time').time())}.jpg",
                        file_type="image/jpeg",
                    )
                    print(f"✅ Image uploaded to Storage: {storage_url}")
                except Exception as e:
                    print(f"⚠️ Failed to upload to Storage: {e}")
                    storage_url = None

                # Step 2: Save to Firebase Firestore
                print("📝 Saving image metadata to Firebase Firestore...")
                await save_conversation_message_to_firestore(
                    user_id=canonical_user_id,
                    role="operator",
                    text="[Image Message from Operator]",
                    conversation_id=conversation_id,
                    phone_number=phone_number,  # NOW PASSING PHONE_NUMBER
                    metadata={
                        "operator_id": operator_id,
                        "handled_by": "human",
                        "type": "image",
                        "image_data": message,  # Store full base64 as backup
                        "image_url": storage_url,  # Store the public URL with key name 'image_url' for easy retrieval
                        "message_length": len(message),
                    },
                )

                # Step 3: Send image via Qiscus
                print(f"🖼️ Sending image via Qiscus to ...{str(user_id)[-4:]}...")
                try:
                    if storage_url:
                        # Send as native image message (displays in gallery on phone, not just a link)
                        await adapter.send_image_message(canonical_user_id, storage_url, caption="صورة من المشغل")
                        print("✅ Sent image as native image message via Qiscus")
                    else:
                        # Fallback: send text notification if storage upload failed
                        text_notification = "تم استلام صورة من المشغل. يرجى فتح لوحة المعلومات لعرضها."
                        await adapter.send_text_message(canonical_user_id, text_notification)
                        print("✅ Sent text notification (storage upload failed)")
                except Exception as e:
                    print(f"⚠️ Failed to send via Qiscus: {e}")
                    import traceback

                    traceback.print_exc()

                print(f"✅ Image message processed and sent for ...{str(user_id)[-4:]}")

                completed_ok = True
                return {
                    "success": True,
                    "message": "Image message sent successfully",
                    "storage_url": storage_url,
                    **manual_meta,
                }

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

                # Await WhatsApp send (single delivery; avoids duplicate background tasks)
                try:
                    result = await adapter.send_text_message(canonical_user_id, message)
                    if not isinstance(result, dict) or not result.get("success"):
                        err = (result or {}).get("error") if isinstance(result, dict) else "send failed"
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
            release = await self.release_conversation(conversation_id, user_id)
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
