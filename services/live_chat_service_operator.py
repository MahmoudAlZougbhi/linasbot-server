from __future__ import annotations

from typing import Any

from services.live_chat_operator_pause_session import (
    live_chat_manual_mode_db_session,
    operator_thread_status,
)
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
        paused_this_send = False
        already_paused = False
        control_source_channel = source_channel
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
                    "delivery_status": "sending",
                    "client_message_id": fingerprint,
                }

            from services.live_chat_operator_social_delivery import is_social_live_chat_user
            from services.live_chat_operator_text_delivery import (
                deliver_saved_operator_text,
                operator_media_not_supported,
            )

            if is_social_live_chat_user(user_id) and message_type not in {"text", "voice", "image"}:
                return {
                    "success": False,
                    "error": "Unsupported message type for social Live Chat",
                }
            media_block = operator_media_not_supported(user_id, message_type)
            if media_block is not None:
                return media_block

            # Server-authoritative: pause AI before outbound so in-flight AI cannot win the race.
            # Meta/TikTok/Web must not open WhatsApp Postgres (pool wait + hold during Firestore).
            manual_meta: dict[str, Any] = {}
            try:
                from services.requests.manual_mode import activate_manual_mode

                with live_chat_manual_mode_db_session(
                    user_id=user_id,
                    tenant_id=tenant_id,
                    source_channel=source_channel,
                ) as (wa_session, control_source_channel):
                    pause_result = await activate_manual_mode(
                        conversation_id=conversation_id,
                        user_id=user_id,
                        actor_user_id=operator_id,
                        tenant_id=tenant_id,
                        operator_name=operator_name,
                        request_id=request_id,
                        source_channel=control_source_channel,
                        session=wa_session,
                    )
                manual_meta = {
                    "manual_mode_activated": pause_result.activated,
                    "manual_mode_already_active": pause_result.already_active,
                    "control_epoch": pause_result.control_epoch,
                    "status": operator_thread_status(
                        paused=bool(pause_result.activated or pause_result.already_active)
                    ),
                }
                paused_this_send = bool(pause_result.activated and not pause_result.already_active)
                already_paused = bool(pause_result.already_active)
            except Exception as pause_err:
                print(f"⚠️ manual_mode pause before send failed: {pause_err}")
                return {
                    "success": False,
                    "error": f"Failed to pause AI before send: {pause_err}",
                    "status": "bot",
                }

            canonical_user_id, normalized_phone = get_canonical_user_id_and_phone(user_id)
            await self._refresh_operator_thread_index(canonical_user_id, conversation_id)
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
                finished = await self._finish_operator_send(
                    result,
                    manual_meta=manual_meta,
                    paused_this_send=paused_this_send,
                    already_paused=already_paused,
                    conversation_id=conversation_id,
                    user_id=user_id,
                    operator_id=operator_id,
                    tenant_id=tenant_id,
                    request_id=request_id,
                    source_channel=control_source_channel,
                )
                completed_ok = bool(finished.get("success"))
                return finished

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
                finished = await self._finish_operator_send(
                    result,
                    manual_meta=manual_meta,
                    paused_this_send=paused_this_send,
                    already_paused=already_paused,
                    conversation_id=conversation_id,
                    user_id=user_id,
                    operator_id=operator_id,
                    tenant_id=tenant_id,
                    request_id=request_id,
                    source_channel=control_source_channel,
                )
                completed_ok = bool(finished.get("success"))
                return finished

            else:  # Default to text
                # Save to Firestore first (SSE broadcasts immediately → message appears in UI fast)
                await save_conversation_message_to_firestore(
                    user_id=canonical_user_id,
                    role="operator",
                    text=message,
                    conversation_id=conversation_id,
                    phone_number=phone_number,
                    metadata={
                        "operator_id": operator_id,
                        "handled_by": "human",
                        "client_message_id": fingerprint,
                        "delivery_status": "sending",
                    },
                )
                print("✅ Saved operator message to Firestore")

                delivery = await deliver_saved_operator_text(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    canonical_user_id=canonical_user_id,
                    conversation_id=conversation_id,
                    text=message,
                    adapter=adapter,
                    idempotency_key=idempotency_key or fingerprint,
                )
                from services.live_chat_operator_delivery_status import (
                    compose_operator_text_result,
                    finalize_operator_delivery_state,
                )

                if not delivery.get("success"):
                    err = str(delivery.get("error") or "delivery_failed")
                    print(f"⚠️ Operator send failed after save: {err}")
                    await finalize_operator_delivery_state(
                        user_id=user_id,
                        conversation_id=conversation_id,
                        client_message_id=fingerprint,
                        delivery_status="failed",
                        error=err,
                        tenant_id=tenant_id,
                    )
                    return await self._finish_operator_send(
                        {
                            "success": False,
                            "error": f"Message saved locally but delivery failed: {err}",
                            "delivered": False,
                            "delivery_status": "failed",
                            "client_message_id": fingerprint,
                        },
                        manual_meta=manual_meta,
                        paused_this_send=paused_this_send,
                        already_paused=already_paused,
                        conversation_id=conversation_id,
                        user_id=user_id,
                        operator_id=operator_id,
                        tenant_id=tenant_id,
                        request_id=request_id,
                        source_channel=control_source_channel,
                    )
                completed_ok = True
                payload = compose_operator_text_result(delivery, manual_meta, client_message_id=fingerprint)
                await finalize_operator_delivery_state(
                    user_id=user_id,
                    conversation_id=conversation_id,
                    client_message_id=fingerprint,
                    delivery_status=str(payload.get("delivery_status") or "sent"),
                    tenant_id=tenant_id,
                )
                return payload

        except Exception as e:
            print(f"❌ Error sending operator message: {e}")
            import traceback

            traceback.print_exc()
            if paused_this_send:
                await self._undo_manual_pause_after_failed_send(
                    conversation_id=conversation_id,
                    user_id=user_id,
                    operator_id=operator_id,
                    tenant_id=tenant_id,
                    request_id=request_id,
                    source_channel=control_source_channel,
                )
                return {
                    "success": False,
                    "error": str(e),
                    "status": "bot",
                    "manual_mode_undone_after_failed_delivery": True,
                }
            return {
                "success": False,
                "error": str(e),
                "status": operator_thread_status(paused=already_paused),
            }
        finally:
            if lock_ref is not None and not completed_ok:
                await _release_operator_idempotency_lock(db, lock_ref)

    async def _refresh_operator_thread_index(self, user_id: str, conversation_id: str) -> None:
        refresh = getattr(self, "_refresh_index_for_conversation", None)
        if not callable(refresh):
            return
        try:
            await refresh(user_id, conversation_id)
        except Exception as refresh_err:
            print(f"⚠️ live-chat index refresh after operator control failed: {refresh_err}")

    async def _finish_operator_send(
        self,
        result: dict[str, Any],
        *,
        manual_meta: dict[str, Any],
        paused_this_send: bool,
        already_paused: bool,
        conversation_id: str,
        user_id: str,
        operator_id: str,
        tenant_id: str | None,
        request_id: str | None,
        source_channel: str | None,
    ) -> dict[str, Any]:
        payload = {**manual_meta, **(result or {})}
        if payload.get("success"):
            payload["status"] = operator_thread_status(paused=True)
            return payload
        if paused_this_send:
            await self._undo_manual_pause_after_failed_send(
                conversation_id=conversation_id,
                user_id=user_id,
                operator_id=operator_id,
                tenant_id=tenant_id,
                request_id=request_id,
                source_channel=source_channel,
            )
            payload["manual_mode_undone_after_failed_delivery"] = True
            payload["status"] = "bot"
            return payload
        payload["status"] = operator_thread_status(paused=already_paused)
        return payload

    async def _undo_manual_pause_after_failed_send(
        self,
        *,
        conversation_id: str,
        user_id: str,
        operator_id: str,
        tenant_id: str | None,
        request_id: str | None,
        source_channel: str | None,
    ) -> None:
        """Undo a pause we just set because the outbound never reached the customer."""
        try:
            from services.requests.manual_mode import resume_manual_mode

            with live_chat_manual_mode_db_session(
                user_id=user_id,
                tenant_id=tenant_id,
                source_channel=source_channel,
            ) as (wa_session, channel):
                await resume_manual_mode(
                    conversation_id=conversation_id,
                    user_id=user_id,
                    actor_user_id=operator_id,
                    tenant_id=tenant_id,
                    request_id=request_id,
                    source_channel=channel,
                    session=wa_session,
                )
        except Exception as undo_err:
            print(f"⚠️ undo manual pause after failed social send failed: {undo_err}")

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
            from services.requests.manual_mode import resume_manual_mode

            with live_chat_manual_mode_db_session(
                user_id=user_id,
                tenant_id=tenant_id,
                source_channel=source_channel,
            ) as (wa_session, channel):
                result = await resume_manual_mode(
                    conversation_id=conversation_id,
                    user_id=user_id,
                    actor_user_id=operator_id,
                    tenant_id=tenant_id,
                    request_id=request_id,
                    source_channel=channel,
                    session=wa_session,
                )

            release_fn = getattr(self, "release_conversation", None)
            if callable(release_fn):
                release = await release_fn(conversation_id, user_id)
            else:
                release = {"success": False, "error": "release_conversation unavailable"}
            await self._refresh_operator_thread_index(user_id, conversation_id)
            return {
                "success": True,
                "message": "AI resumed for conversation",
                "conversation_id": conversation_id,
                "status": "bot",
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
