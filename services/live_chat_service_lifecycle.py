from __future__ import annotations

import asyncio
import datetime
from typing import Any

import config
from services.live_chat_contracts import (
    utc_now,
)
from utils.utils import (
    get_canonical_user_id_and_phone,
    get_firestore_db,
    set_human_takeover_status,
)


class LiveChatLifecycleMixin:
    """End, reopen, takeover, release, and read-state lifecycle."""

    APP_ID: Any
    STATE_ARCHIVED: Any
    STATE_ASSIGNED: Any
    STATE_BOT_ACTIVE: Any
    STATE_RESOLVED: Any
    _get_doc_with_timeout: Any
    _index_collection: Any
    _index_signature_cache: Any
    _refresh_index_for_conversation: Any
    _resolve_conversation_doc_ref: Any
    invalidate_cache: Any
    operator_sessions: Any

    async def end_conversation(
        self, conversation_id: str, user_id: str, operator_id: str, adapter: Any | None = None
    ) -> dict[str, Any]:
        """
        Mark conversation as resolved/ended
        - Sets status to 'resolved'
        - Records who resolved it and when
        - Removes from active view
        - Sends notification to customer
        - Can be reopened if customer messages again
        """
        try:
            canonical_user_id, _ = get_canonical_user_id_and_phone(user_id)
            db = get_firestore_db()
            if not db:
                return {"success": False, "error": "Firestore not initialized"}

            app_id = "linas-ai-bot-backend"
            conv_ref = (
                db.collection("artifacts")
                .document(app_id)
                .collection("users")
                .document(canonical_user_id)
                .collection(config.FIRESTORE_CONVERSATIONS_COLLECTION)
                .document(conversation_id)
            )

            # Update conversation status
            update_data = {
                "status": "resolved",
                "resolved_at": utc_now(),
                "resolved_by": operator_id,
                "human_takeover_active": False,
                "operator_id": None,
                "conversation_state": self.STATE_RESOLVED,
            }

            print(f"🔄 Updating conversation {conversation_id} with data: {update_data}")
            # ✅ Use asyncio.to_thread to prevent blocking the event loop
            await asyncio.to_thread(conv_ref.update, update_data)
            print(f"✅ Firebase updated successfully for conversation {conversation_id}")

            # Verify the update
            updated_doc = await asyncio.to_thread(conv_ref.get)
            if updated_doc.exists:
                updated_data = updated_doc.to_dict()
                print(
                    f"✅ Verified: status = {updated_data.get('status')}, resolved_by = {updated_data.get('resolved_by')}"
                )

            # Update in-memory state
            config.user_in_human_takeover_mode[canonical_user_id] = False
            if conversation_id in self.operator_sessions:
                del self.operator_sessions[conversation_id]

            # Clear current_conversation_id so next message creates a new conversation
            if canonical_user_id in config.user_data_whatsapp:
                config.user_data_whatsapp[canonical_user_id].pop("current_conversation_id", None)
                print(
                    f"🔄 Cleared current_conversation_id for {canonical_user_id} - next message will start new conversation"
                )

            # Invalidate cache
            self.invalidate_cache()

            # Refresh index to reflect resolved state
            await self._refresh_index_for_conversation(canonical_user_id, conversation_id)

            # Send notification to customer
            if adapter:
                try:
                    # Multilingual end conversation messages
                    end_messages = {
                        "ar": "شكراً لتواصلك معنا! تم إنهاء المحادثة. إذا كان لديك أي استفسار آخر، لا تتردد في مراسلتنا مجدداً. 🌟",
                        "en": "Thank you for contacting us! This conversation has been ended. If you have any other questions, feel free to message us again. 🌟",
                        "fr": "Merci de nous avoir contactés! Cette conversation est terminée. Si vous avez d'autres questions, n'hésitez pas à nous écrire à nouveau. 🌟",
                    }

                    # Get user's preferred language from config
                    user_lang = config.user_data_whatsapp.get(canonical_user_id, {}).get("user_preferred_lang", "ar")
                    notification_message = end_messages.get(user_lang, end_messages["ar"])

                    # Send notification via WhatsApp
                    await adapter.send_text_message(canonical_user_id, notification_message)
                    print(f"✅ Sent end conversation notification to customer ...{str(user_id)[-4:]}")

                    # Save notification to Firebase
                    from utils.utils import save_conversation_message_to_firestore

                    await save_conversation_message_to_firestore(
                        user_id=canonical_user_id,
                        role="ai",
                        text=notification_message,
                        conversation_id=conversation_id,
                        metadata={"type": "end_conversation_notification", "operator_id": operator_id},
                    )
                except Exception as e:
                    print(f"⚠️ Failed to send end conversation notification: {e}")

            print(f"✅ Conversation {conversation_id} marked as resolved by {operator_id}")

            return {
                "success": True,
                "message": "Conversation ended successfully",
                "conversation_id": conversation_id,
                "status": "resolved",
            }

        except Exception as e:
            print(f"❌ Error ending conversation: {e}")
            import traceback

            traceback.print_exc()
            return {"success": False, "error": str(e)}

    async def reopen_conversation(self, conversation_id: str, user_id: str) -> dict[str, Any]:
        """
        Reopen a resolved conversation (auto-called when customer messages again)
        """
        try:
            canonical_user_id, _ = get_canonical_user_id_and_phone(user_id)
            db = get_firestore_db()
            if not db:
                return {"success": False, "error": "Firestore not initialized"}

            app_id = "linas-ai-bot-backend"
            conv_ref = (
                db.collection("artifacts")
                .document(app_id)
                .collection("users")
                .document(canonical_user_id)
                .collection(config.FIRESTORE_CONVERSATIONS_COLLECTION)
                .document(conversation_id)
            )

            # Reopen conversation - use asyncio.to_thread to prevent blocking
            await asyncio.to_thread(
                conv_ref.update,
                {
                    "status": "active",
                    "reopened_at": utc_now(),
                    "resolved_at": None,
                    "resolved_by": None,
                    "conversation_state": self.STATE_BOT_ACTIVE,
                    "human_takeover_active": False,
                    "operator_id": None,
                },
            )

            print(f"✅ Conversation {conversation_id} reopened (customer messaged again)")

            # Refresh index so UI picks up the reopened state
            await self._refresh_index_for_conversation(canonical_user_id, conversation_id)

            return {"success": True, "message": "Conversation reopened", "conversation_id": conversation_id}

        except Exception as e:
            print(f"❌ Error reopening conversation: {e}")
            return {"success": False, "error": str(e)}

    async def _auto_archive_conversation(self, user_id: str, conversation_id: str) -> None:
        """
        Auto-archive conversations older than 6 hours
        """
        try:
            db = get_firestore_db()
            if not db:
                return

            app_id = "linas-ai-bot-backend"
            conv_ref = (
                db.collection("artifacts")
                .document(app_id)
                .collection("users")
                .document(user_id)
                .collection(config.FIRESTORE_CONVERSATIONS_COLLECTION)
                .document(conversation_id)
            )

            # ✅ Use asyncio.to_thread to prevent blocking the event loop
            await asyncio.to_thread(
                conv_ref.update,
                {
                    "status": "archived",
                    "archived_at": utc_now(),
                    "archived_reason": "auto_6h_timeout",
                    "conversation_state": self.STATE_ARCHIVED,
                    "human_takeover_active": False,
                    "operator_id": None,
                },
            )

            print(f"📦 Auto-archived conversation {conversation_id} (6-hour timeout)")

            # Refresh index so the archive is reflected in lists
            await self._refresh_index_for_conversation(user_id, conversation_id)

        except Exception as e:
            print(f"⚠️ Error auto-archiving conversation: {e}")

    async def takeover_conversation(
        self, conversation_id: str, user_id: str, operator_id: str, operator_name: str | None = None
    ) -> dict[str, Any]:
        """Operator takes over a conversation"""
        try:
            canonical_user_id, _ = get_canonical_user_id_and_phone(user_id)
            db = get_firestore_db()
            resolved_user_id = canonical_user_id
            if db:
                users_coll = db.collection("artifacts").document(self.APP_ID).collection("users")
                conv_ref = (
                    users_coll.document(canonical_user_id)
                    .collection(config.FIRESTORE_CONVERSATIONS_COLLECTION)
                    .document(conversation_id)
                )
                conv_snap = await asyncio.to_thread(conv_ref.get)
                if not conv_snap.exists and user_id != canonical_user_id:
                    conv_ref = (
                        users_coll.document(user_id)
                        .collection(config.FIRESTORE_CONVERSATIONS_COLLECTION)
                        .document(conversation_id)
                    )
                    conv_snap = await asyncio.to_thread(conv_ref.get)
                    if conv_snap.exists:
                        resolved_user_id = user_id
                if not conv_snap.exists:
                    return {"success": False, "error": "Conversation not found. Check user_id and conversation_id."}
            await set_human_takeover_status(resolved_user_id, conversation_id, True, operator_id, operator_name)
            config.user_in_human_takeover_mode[resolved_user_id] = True
            self.operator_sessions[conversation_id] = operator_id

            # Ensure canonical state is written
            if db and conv_ref is not None:
                await asyncio.to_thread(
                    conv_ref.update,
                    {
                        "conversation_state": self.STATE_ASSIGNED,
                        "last_updated": utc_now(),
                    },
                )

            # Refresh index
            await self._refresh_index_for_conversation(resolved_user_id, conversation_id)

            # Invalidate cache
            self.invalidate_cache()

            print(f"✅ Operator {operator_id} took over conversation {conversation_id}")

            return {
                "success": True,
                "message": "Conversation taken over successfully",
                "conversation_id": conversation_id,
                "operator_id": operator_id,
            }

        except Exception as e:
            print(f"❌ Error taking over conversation: {e}")
            return {"success": False, "error": str(e)}

    async def release_conversation(self, conversation_id: str, user_id: str) -> dict[str, Any]:
        """Release conversation back to bot"""
        try:
            db = get_firestore_db()
            conv_ref = None
            resolved_user_id = user_id
            if db:
                conv_ref, conv_snap, resolved_user_id = await self._resolve_conversation_doc_ref(
                    db, user_id, conversation_id
                )
                if not conv_snap.exists:
                    return {
                        "success": False,
                        "error": "Conversation not found. Check user_id and conversation_id.",
                    }
            else:
                resolved_user_id, _ = get_canonical_user_id_and_phone(user_id)
            await set_human_takeover_status(resolved_user_id, conversation_id, False, request_user_id=user_id)
            if conversation_id in self.operator_sessions:
                del self.operator_sessions[conversation_id]

            # Ensure canonical state is written
            if db and conv_ref is not None:
                await asyncio.to_thread(
                    conv_ref.update,
                    {
                        "conversation_state": self.STATE_BOT_ACTIVE,
                        "last_updated": utc_now(),
                        "operator_id": None,
                    },
                )

            # Force index update: clear signature cache so refresh doesn't skip write, update index directly
            self._index_signature_cache.pop(conversation_id, None)
            if db:
                idx_ref = self._index_collection(db).document(conversation_id)
                try:
                    try:
                        _cd_mins = int(getattr(config, "POST_TAKEOVER_ESCALATION_COOLDOWN_MINUTES", 45))
                    except (TypeError, ValueError):
                        _cd_mins = 45
                    _post_rel = utc_now() + datetime.timedelta(minutes=_cd_mins)

                    def _merge_release_index() -> None:
                        idx_ref.set(
                            {
                                "conversation_state": self.STATE_BOT_ACTIVE,
                                "operator_id": None,
                                "human_takeover_active": False,
                                "post_release_escalation_suppressed_until": _post_rel,
                            },
                            merge=True,
                        )

                    await asyncio.to_thread(_merge_release_index)
                except Exception as idx_err:
                    print(f"⚠️ Direct index update on release failed: {idx_err}")
            await self._refresh_index_for_conversation(resolved_user_id, conversation_id)

            # Invalidate cache
            self.invalidate_cache()

            # Same-process WhatsApp session: prime cooldown so AI anti-re-escalation applies before next Firestore read
            try:
                from utils.utils import _build_user_id_variants_for_release, set_post_takeover_escalation_cooldown

                canonical_uid, _ = get_canonical_user_id_and_phone(user_id)
                for vid in _build_user_id_variants_for_release(resolved_user_id, user_id, canonical_uid):
                    set_post_takeover_escalation_cooldown(config.user_data_whatsapp[vid])
            except Exception as mem_cd_err:
                print(f"⚠️ Release in-memory cooldown prime skipped: {mem_cd_err}")

            print(f"✅ Conversation {conversation_id} released back to bot")

            return {
                "success": True,
                "message": "Conversation released to bot successfully",
                "conversation_id": conversation_id,
            }

        except Exception as e:
            print(f"❌ Error releasing conversation: {e}")
            return {"success": False, "error": str(e)}

    async def mark_conversation_read(self, user_id: str, conversation_id: str) -> dict[str, Any]:
        """
        Mark a conversation as read (operator opened it).
        Sets unread_count=0 in Firestore so it persists across refresh/update.
        """
        try:
            canonical_user_id, _ = get_canonical_user_id_and_phone(user_id)
            db = get_firestore_db()
            if not db:
                return {"success": False, "error": "Firestore not initialized"}

            conv_ref = (
                db.collection("artifacts")
                .document(self.APP_ID)
                .collection("users")
                .document(canonical_user_id)
                .collection(config.FIRESTORE_CONVERSATIONS_COLLECTION)
                .document(conversation_id)
            )
            conv_snap = await self._get_doc_with_timeout(conv_ref)
            if not conv_snap.exists:
                return {"success": False, "error": "Conversation not found"}

            current = conv_snap.to_dict() or {}
            if int(current.get("unread_count") or 0) == 0:
                return {"success": True, "message": "Already read"}

            await asyncio.to_thread(conv_ref.update, {"unread_count": 0})
            await self._refresh_index_for_conversation(canonical_user_id, conversation_id)
            self.invalidate_cache()
            return {"success": True, "message": "Marked as read"}
        except Exception as e:
            print(f"❌ Error marking conversation read: {e}")
            return {"success": False, "error": str(e)}
