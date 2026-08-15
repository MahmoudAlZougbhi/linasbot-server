"""Smart Follow-Up delivery for website chat visitors."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from db.models.whatsapp_smart_followup import WhatsAppSmartFollowUpJob, WhatsAppSmartFollowUpSettings
from services.requests.constants import SOURCE_CHANNEL_WEB_CHAT
from services.smart_followup.types import FollowUpConversationView, FollowUpSendResult
from services.web_chat.processor import compose_web_user_id
from services.web_chat.store import web_chat_store


class WebFollowUpAdapter:
    channel = SOURCE_CHANNEL_WEB_CHAT

    def load_conversation(
        self,
        session: Session,
        *,
        job: WhatsAppSmartFollowUpJob,
    ) -> FollowUpConversationView | None:
        ctx = dict(job.channel_context or {})
        last_inbound = ctx.get("last_inbound_at")
        opened = None
        if isinstance(last_inbound, datetime):
            opened = last_inbound
        elif isinstance(last_inbound, str) and last_inbound.strip():
            try:
                opened = datetime.fromisoformat(last_inbound.replace("Z", "+00:00"))
            except ValueError:
                opened = None
        return FollowUpConversationView(
            channel=self.channel,
            tenant_id=job.tenant_id,
            conversation_id=job.conversation_id,
            connection_id=job.connection_id,
            control_epoch=job.control_epoch,
            control_state="AI_ACTIVE",
            service_window_opens_at=opened,
            last_inbound_at=opened,
            profile_name=str(ctx.get("profile_name") or "Website visitor"),
            user_id=str(ctx.get("user_id") or ""),
            social_sender_id=str(ctx.get("social_sender_id") or ""),
            asset_id=str(ctx.get("asset_id") or job.connection_id),
            meta_binding_id=str(ctx.get("meta_binding_id") or job.connection_id),
            trigger_ref=str(ctx.get("trigger_ref") or ""),
        )

    def evaluate_channel_eligibility(
        self,
        session: Session,
        *,
        job: WhatsAppSmartFollowUpJob,
        settings: WhatsAppSmartFollowUpSettings | None,
        conv: FollowUpConversationView,
        now: Any | None = None,
    ) -> tuple[bool, str]:
        from services.web_chat.processor import evaluate_web_ai_eligibility
        from services.web_chat.store import web_chat_store

        widget = web_chat_store.get_or_create_widget(job.tenant_id)
        eligible, reason = evaluate_web_ai_eligibility(job.tenant_id, widget)
        if not eligible:
            return False, reason or "not_eligible"
        visitor_id = str(conv.social_sender_id or "").strip()
        if not visitor_id or web_chat_store.get_visitor(visitor_id) is None:
            return False, "visitor_session_missing"
        return True, "ok"

    async def send_followup(
        self,
        session: Session,
        *,
        job: WhatsAppSmartFollowUpJob,
        conv: FollowUpConversationView,
        reply_text: str,
        idempotency_key: str,
    ) -> FollowUpSendResult:
        visitor_id = str(conv.social_sender_id or "").strip()
        if not visitor_id:
            return FollowUpSendResult(ok=False, delivery="permanent_block", error="missing_visitor")
        try:
            web_chat_store.queue_assistant_message(visitor_id, reply_text)
            user_id = compose_web_user_id(visitor_id)
            from utils.utils import save_conversation_message_to_firestore

            user_data = {"tenant_id": job.tenant_id, "channel": "web"}
            await save_conversation_message_to_firestore(
                user_id,
                reply_text,
                is_user=False,
                user_data=user_data,
                channel="web",
                handled_by="smart_followup",
                metadata={"channel": "web", "source": SOURCE_CHANNEL_WEB_CHAT, "idempotency_key": idempotency_key},
            )
            return FollowUpSendResult(ok=True, delivery="delivered", provider_message_id=idempotency_key)
        except Exception as exc:
            return FollowUpSendResult(ok=False, delivery="failed", error=type(exc).__name__)
