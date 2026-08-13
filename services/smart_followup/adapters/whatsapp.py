"""WhatsApp Cloud Smart Follow-Up adapter."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from db.models.whatsapp_smart_followup import WhatsAppSmartFollowUpJob, WhatsAppSmartFollowUpSettings
from services.requests.constants import SOURCE_CHANNEL_WHATSAPP_CLOUD
from services.smart_followup.types import FollowUpConversationView, FollowUpSendResult
from services.smart_followup.window_rules import window_allows_send
from services.whatsapp_cloud.config import get_whatsapp_cloud_flags
from services.whatsapp_cloud.entitlement import evaluate_ai_eligibility, tenant_has_whatsapp_pilot
from services.whatsapp_cloud.graph_client import WhatsAppGraphError, send_text_message
from services.whatsapp_cloud.observability import emit_wa_event, record_analytics_channel_usage
from services.whatsapp_cloud.repository import WhatsAppCloudRepository


class WhatsAppFollowUpAdapter:
    channel = SOURCE_CHANNEL_WHATSAPP_CLOUD

    def load_conversation(
        self,
        session: Session,
        *,
        job: WhatsAppSmartFollowUpJob,
    ) -> FollowUpConversationView | None:
        repo = WhatsAppCloudRepository(session)
        conv = repo.get_tenant_conversation(tenant_id=job.tenant_id, conversation_id=job.conversation_id)
        if conv is None:
            return None
        return FollowUpConversationView(
            channel=self.channel,
            tenant_id=job.tenant_id,
            conversation_id=conv.id,
            connection_id=job.connection_id,
            control_epoch=int(conv.control_epoch),
            control_state=str(conv.control_state),
            service_window_opens_at=conv.service_window_opens_at,
            last_inbound_at=conv.last_inbound_at,
            profile_name=str(conv.customer_profile_name or ""),
            customer_wa_id=str(conv.customer_wa_id or ""),
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
        now_dt = now if isinstance(now, datetime) else datetime.now(UTC)
        flags = get_whatsapp_cloud_flags()
        if not flags.ai_replies_enabled:
            return False, "ai_replies_flag_off"
        if not flags.outbound_sends_enabled:
            return False, "outbound_flag_off"

        repo = WhatsAppCloudRepository(session)
        conn = repo.get_connection(job.connection_id)
        if conn is None:
            return False, "connection_missing"
        if conn.tenant_id != job.tenant_id:
            return False, "tenant_mismatch"
        if conn.lifecycle_status != "connected":
            return False, "connection_not_connected"
        if conn.lifecycle_status in {"revoked", "failed", "needs_attention", "disconnected"}:
            return False, f"connection_{conn.lifecycle_status}"
        if not conn.ai_default_enabled:
            return False, "ai_default_off"
        if not flags.public_availability:
            if flags.require_pilot_entitlement and not tenant_has_whatsapp_pilot(session, job.tenant_id):
                return False, "pilot_required"

        if conv.control_state != "AI_ACTIVE":
            return False, "conversation_paused"
        if int(conv.control_epoch) != int(job.control_epoch):
            return False, "epoch_changed"

        ok_window, window_reason = window_allows_send(conv=conv, now=now_dt)
        if not ok_window:
            return False, window_reason or "window_closed"

        ai_ok, ai_reason = evaluate_ai_eligibility(session, conn)
        if not ai_ok:
            return False, ai_reason or "ai_ineligible"
        return True, "eligible"

    async def send_followup(
        self,
        session: Session,
        *,
        job: WhatsAppSmartFollowUpJob,
        conv: FollowUpConversationView,
        reply_text: str,
        idempotency_key: str,
    ) -> FollowUpSendResult:
        repo = WhatsAppCloudRepository(session)
        conn = repo.get_connection(job.connection_id)
        if conn is None:
            return FollowUpSendResult(status="failed", reason="connection_missing")
        wa_conv = repo.get_tenant_conversation(tenant_id=job.tenant_id, conversation_id=job.conversation_id)
        if wa_conv is None:
            return FollowUpSendResult(status="failed", reason="conversation_missing")

        intent, created = repo.create_outbound_intent(
            tenant_id=job.tenant_id,
            connection_id=conn.id,
            conversation_id=wa_conv.id,
            idempotency_key=idempotency_key,
            control_epoch=int(job.control_epoch),
            triggering_inbound_message_id=None,
            source="SMART_FOLLOWUP",
        )
        if intent is None:
            return FollowUpSendResult(status="failed", reason="intent_create_failed")
        if not created and intent.dispatch_state in {"sent", "sending", "suppressed", "reconciliation_required"}:
            if intent.dispatch_state == "sent":
                return FollowUpSendResult(
                    status="sent",
                    reason="duplicate_outbound_intent",
                    provider_message_id=intent.provider_wamid,
                )
            return FollowUpSendResult(
                status="skipped",
                reason="duplicate_outbound_intent",
                provider_message_id=intent.provider_wamid,
            )

        repo.update_outbound_intent(intent, dispatch_state="sending", control_epoch_at_send=int(wa_conv.control_epoch))
        try:
            token = repo.load_access_token(conn)
        except PermissionError:
            repo.update_outbound_intent(intent, dispatch_state="failed", error_code="credential_unavailable")
            return FollowUpSendResult(status="failed", reason="credential_unavailable")

        try:
            result = await send_text_message(
                access_token=token,
                phone_number_id=conn.phone_number_id,
                to_wa_id=wa_conv.customer_wa_id,
                text=reply_text,
            )
        except WhatsAppGraphError as exc:
            state = (
                "reconciliation_required"
                if (
                    (exc.retryable and exc.http_status in {408, 504, None})
                    or "timeout" in exc.message.lower()
                    or exc.code.endswith("timeout")
                )
                else "failed"
            )
            repo.update_outbound_intent(
                intent,
                dispatch_state=state,
                error_code=exc.code,
                error_detail=exc.message[:255],
            )
            return FollowUpSendResult(
                status="reconciliation_required" if state == "reconciliation_required" else "failed",
                reason=str(exc.code),
                detail=exc.message[:255],
                reconciliation=state == "reconciliation_required",
            )
        except Exception as exc:
            repo.update_outbound_intent(
                intent,
                dispatch_state="reconciliation_required",
                error_code=type(exc).__name__,
                error_detail="ambiguous_after_submit",
            )
            return FollowUpSendResult(
                status="reconciliation_required",
                reason="ambiguous_after_submit",
                detail=type(exc).__name__,
                reconciliation=True,
            )

        messages = result.get("messages") if isinstance(result, dict) else None
        wamid = ""
        if isinstance(messages, list) and messages:
            wamid = str((messages[0] or {}).get("id") or "")

        repo.update_outbound_intent(intent, dispatch_state="sent", provider_wamid=wamid or None)
        repo.insert_message(
            tenant_id=job.tenant_id,
            connection_id=conn.id,
            conversation_id=wa_conv.id,
            provider_message_id=wamid or f"local:sfu:{job.id}",
            origin="CLOUD_API",
            direction="outbound",
            message_type="text",
            content_preview=reply_text[:80],
            status="sent",
            meta={"source": "SMART_FOLLOWUP", "goal": job.goal, "step_index": int(job.step_index)},
        )
        wa_conv.last_ai_outbound_at = datetime.now(UTC)
        record_analytics_channel_usage(
            tenant_id=job.tenant_id,
            connection_id=conn.id,
            conversation_id=wa_conv.id,
            provider_message_id=wamid or job.id,
            source="smart_followup",
        )
        emit_wa_event(
            "smart_followup_sent",
            tenant_id=job.tenant_id,
            conversation_id=wa_conv.id,
            step_index=int(job.step_index),
            channel=self.channel,
        )
        return FollowUpSendResult(status="sent", reason="sent", provider_message_id=wamid or None)
