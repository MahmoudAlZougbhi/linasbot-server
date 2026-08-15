"""Smart Follow-Up delivery for website chat visitors."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from db.models.whatsapp_smart_followup import WhatsAppSmartFollowUpJob, WhatsAppSmartFollowUpSettings
from services.requests.constants import SOURCE_CHANNEL_WEB_CHAT
from services.smart_followup.types import FollowUpConversationView, FollowUpSendResult
from services.web_chat.flags import web_chat_containment_active
from services.web_chat.followup_delivery import (
    FollowUpSessionBoundaryError,
    deliver_web_followup_message,
)
from services.web_chat.operation_fsm import OperationFsmError
from services.web_chat.processor import compose_web_user_id
from services.web_chat.session_binding import resolve_durable_visitor_binding
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
        from services.web_chat.flags import assert_widget_operational
        from services.web_chat.processor import evaluate_web_ai_eligibility

        if web_chat_containment_active():
            return False, "web_chat_contained"
        widget = web_chat_store.get_or_create_widget(job.tenant_id)
        try:
            assert_widget_operational(widget)
        except ValueError:
            return False, "widget_disabled"
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
        if web_chat_containment_active():
            return FollowUpSendResult(status="skipped", reason="web_chat_contained")
        visitor_id = str(conv.social_sender_id or "").strip()
        if not visitor_id:
            return FollowUpSendResult(status="skipped", reason="missing_visitor")
        widget_key = str(conv.asset_id or job.connection_id or "").strip()
        try:
            resolve_durable_visitor_binding(
                store=web_chat_store,
                visitor_id=visitor_id,
                expected_tenant_id=job.tenant_id,
                expected_widget_key=widget_key,
            )
        except FollowUpSessionBoundaryError as exc:
            return FollowUpSendResult(status="failed", reason=exc.code, detail=exc.message)
        visitor = web_chat_store.get_visitor(visitor_id)
        authority_hash = str(getattr(visitor, "authority_hash", "") or "") if visitor is not None else ""
        bound_reservation = str(job.reservation_id or "").strip()
        if not bound_reservation:
            return FollowUpSendResult(
                status="failed",
                reason="reservation_required",
                detail="Follow-up delivery requires a bound credit reservation.",
            )
        try:
            delivery = await deliver_web_followup_message(
                tenant_id=job.tenant_id,
                visitor_id=visitor_id,
                user_id=compose_web_user_id(visitor_id),
                conversation_id=job.conversation_id,
                reply_text=reply_text,
                idempotency_key=idempotency_key,
                widget_key=widget_key,
                authority_hash=authority_hash,
                reservation_id=bound_reservation,
            )
            return FollowUpSendResult(
                status="sent",
                reason="duplicate_delivery" if delivery.status == "already_delivered" else "sent",
                provider_message_id=idempotency_key,
                billing_captured=delivery.billing_captured,
                billing_pending=delivery.billing_pending,
            )
        except FollowUpSessionBoundaryError as exc:
            return FollowUpSendResult(status="failed", reason=exc.code, detail=exc.message)
        except OperationFsmError as exc:
            return FollowUpSendResult(status="failed", reason=exc.code, detail=exc.message)
        except Exception as exc:
            return FollowUpSendResult(
                status="failed",
                reason="send_failed",
                detail=type(exc).__name__,
            )
