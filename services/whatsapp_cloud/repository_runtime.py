"""WhatsApp Cloud repository conversation/message/pilot ops (LOC split)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from db.models.whatsapp_cloud import (
    WhatsAppAuditEvent,
    WhatsAppConversation,
    WhatsAppMessage,
    WhatsAppOutboundIntent,
    WhatsAppPilotEntitlement,
    WhatsAppWebhookEvent,
)
from services.whatsapp_cloud.repository_helpers import _utcnow


class WhatsAppCloudRepositoryRuntimeMixin:
    """Conversation, webhook idempotency, outbound intent, pilot, and audit helpers."""

    def get_or_create_conversation(
        self,
        *,
        tenant_id: str,
        connection_id: str,
        customer_wa_id: str,
        profile_name: str = "",
    ) -> WhatsAppConversation:
        row = self.session.scalar(
            select(WhatsAppConversation).where(
                WhatsAppConversation.connection_id == connection_id,
                WhatsAppConversation.customer_wa_id == customer_wa_id,
            )
        )
        if row is not None:
            if profile_name and not row.customer_profile_name:
                row.customer_profile_name = profile_name[:255]
                self.session.flush()
            return row
        row = WhatsAppConversation(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            connection_id=connection_id,
            customer_wa_id=customer_wa_id,
            customer_profile_name=(profile_name or "")[:255],
            control_state="AI_ACTIVE",
            control_epoch=1,
        )
        try:
            with self.session.begin_nested():
                self.session.add(row)
                self.session.flush()
        except IntegrityError:
            existing = self.session.scalar(
                select(WhatsAppConversation).where(
                    WhatsAppConversation.connection_id == connection_id,
                    WhatsAppConversation.customer_wa_id == customer_wa_id,
                )
            )
            if existing is None:
                raise
            return existing
        return row

    def pause_conversation(
        self,
        conv: WhatsAppConversation,
        *,
        reason: str,
        actor_user_id: str | None = None,
    ) -> WhatsAppConversation:
        conv.control_state = "HUMAN_PAUSED"
        conv.control_epoch = int(conv.control_epoch) + 1
        conv.pause_reason = reason[:64]
        conv.last_human_outbound_at = _utcnow()
        self.session.flush()
        self.add_audit(
            tenant_id=conv.tenant_id,
            connection_id=conv.connection_id,
            conversation_id=conv.id,
            actor_user_id=actor_user_id,
            event_type="conversation_paused",
            detail={"reason": reason, "control_epoch": conv.control_epoch},
        )
        return conv

    def resume_conversation(
        self,
        conv: WhatsAppConversation,
        *,
        actor_user_id: str,
    ) -> WhatsAppConversation:
        conv.control_state = "AI_ACTIVE"
        conv.control_epoch = int(conv.control_epoch) + 1
        conv.pause_reason = None
        self.session.flush()
        self.add_audit(
            tenant_id=conv.tenant_id,
            connection_id=conv.connection_id,
            conversation_id=conv.id,
            actor_user_id=actor_user_id,
            event_type="conversation_resumed",
            detail={"control_epoch": conv.control_epoch},
        )
        return conv

    def get_tenant_conversation(self, *, tenant_id: str, conversation_id: str) -> WhatsAppConversation | None:
        conv = self.session.get(WhatsAppConversation, conversation_id)
        if conv is None or conv.tenant_id != tenant_id:
            return None
        return conv

    def list_connection_conversations(
        self,
        *,
        tenant_id: str,
        connection_id: str,
        limit: int = 50,
    ) -> list[WhatsAppConversation]:
        lim = max(1, min(int(limit or 50), 100))
        return list(
            self.session.scalars(
                select(WhatsAppConversation)
                .where(
                    WhatsAppConversation.tenant_id == tenant_id,
                    WhatsAppConversation.connection_id == connection_id,
                )
                .order_by(WhatsAppConversation.updated_at.desc())
                .limit(lim)
            )
        )

    # --- messages / idempotency ---
    def claim_webhook_event(
        self,
        *,
        event_key: str,
        event_kind: str,
        payload_hash: str,
        tenant_id: str | None = None,
        connection_id: str | None = None,
    ) -> tuple[WhatsAppWebhookEvent | None, bool]:
        """Return (event, is_new). is_new False means duplicate."""
        existing = self.session.scalar(select(WhatsAppWebhookEvent).where(WhatsAppWebhookEvent.event_key == event_key))
        if existing is not None:
            existing.attempt_count = int(existing.attempt_count) + 1
            self.session.flush()
            return existing, False
        row = WhatsAppWebhookEvent(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            connection_id=connection_id,
            event_key=event_key,
            event_kind=event_kind,
            processing_state="claimed",
            payload_hash=payload_hash,
        )
        try:
            with self.session.begin_nested():
                self.session.add(row)
                self.session.flush()
        except IntegrityError:
            existing = self.session.scalar(
                select(WhatsAppWebhookEvent).where(WhatsAppWebhookEvent.event_key == event_key)
            )
            return existing, False
        return row, True

    def complete_webhook_event(self, event: WhatsAppWebhookEvent, *, state: str = "processed") -> None:
        event.processing_state = state
        event.processed_at = _utcnow()
        self.session.flush()

    def insert_message(
        self,
        *,
        tenant_id: str,
        connection_id: str,
        conversation_id: str,
        provider_message_id: str,
        origin: str,
        direction: str,
        message_type: str,
        content_preview: str | None,
        media_id: str | None = None,
        media_mime: str | None = None,
        meta: dict[str, Any] | None = None,
        status: str = "received",
    ) -> tuple[WhatsAppMessage | None, bool]:
        existing = self.session.scalar(
            select(WhatsAppMessage).where(WhatsAppMessage.provider_message_id == provider_message_id)
        )
        if existing is not None:
            return existing, False
        row = WhatsAppMessage(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            connection_id=connection_id,
            conversation_id=conversation_id,
            provider_message_id=provider_message_id,
            origin=origin,
            direction=direction,
            message_type=message_type,
            status=status,
            content_preview=(content_preview or None),
            media_id=media_id,
            media_mime=media_mime,
            meta=meta or {},
        )
        try:
            with self.session.begin_nested():
                self.session.add(row)
                self.session.flush()
        except IntegrityError:
            existing = self.session.scalar(
                select(WhatsAppMessage).where(WhatsAppMessage.provider_message_id == provider_message_id)
            )
            return existing, False
        return row, True

    def create_outbound_intent(
        self,
        *,
        tenant_id: str,
        connection_id: str,
        conversation_id: str,
        idempotency_key: str,
        control_epoch: int,
        triggering_inbound_message_id: str | None,
        source: str = "AI",
    ) -> tuple[WhatsAppOutboundIntent | None, bool]:
        existing = self.session.scalar(
            select(WhatsAppOutboundIntent).where(WhatsAppOutboundIntent.idempotency_key == idempotency_key)
        )
        if existing is not None:
            return existing, False
        row = WhatsAppOutboundIntent(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            connection_id=connection_id,
            conversation_id=conversation_id,
            idempotency_key=idempotency_key,
            triggering_inbound_message_id=triggering_inbound_message_id,
            control_epoch_at_create=control_epoch,
            source=source,
            dispatch_state="pending",
        )
        try:
            with self.session.begin_nested():
                self.session.add(row)
                self.session.flush()
        except IntegrityError:
            existing = self.session.scalar(
                select(WhatsAppOutboundIntent).where(WhatsAppOutboundIntent.idempotency_key == idempotency_key)
            )
            return existing, False
        return row, True

    def update_outbound_intent(self, intent: WhatsAppOutboundIntent, **fields: Any) -> WhatsAppOutboundIntent:
        for key, value in fields.items():
            setattr(intent, key, value)
        self.session.flush()
        return intent

    # --- pilot entitlement ---
    def get_active_pilot(self, tenant_id: str) -> WhatsAppPilotEntitlement | None:
        return self.session.scalar(
            select(WhatsAppPilotEntitlement).where(
                WhatsAppPilotEntitlement.tenant_id == tenant_id,
                WhatsAppPilotEntitlement.status == "active",
            )
        )

    def grant_pilot(
        self,
        *,
        tenant_id: str,
        granted_by_user_id: str,
        reason: str,
    ) -> WhatsAppPilotEntitlement:
        existing = self.session.scalar(
            select(WhatsAppPilotEntitlement).where(WhatsAppPilotEntitlement.tenant_id == tenant_id)
        )
        if existing is not None:
            existing.status = "active"
            existing.granted_by_user_id = granted_by_user_id
            existing.reason = reason[:255]
            existing.revoked_at = None
            existing.revoked_by_user_id = None
            self.session.flush()
            return existing
        row = WhatsAppPilotEntitlement(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            status="active",
            granted_by_user_id=granted_by_user_id,
            reason=reason[:255],
        )
        self.session.add(row)
        self.session.flush()
        return row

    def revoke_pilot(self, *, tenant_id: str, actor_user_id: str) -> WhatsAppPilotEntitlement | None:
        row = self.session.scalar(
            select(WhatsAppPilotEntitlement).where(WhatsAppPilotEntitlement.tenant_id == tenant_id)
        )
        if row is None:
            return None
        row.status = "revoked"
        row.revoked_at = _utcnow()
        row.revoked_by_user_id = actor_user_id
        self.session.flush()
        return row

    def list_pilots(self, *, status: str | None = "active", limit: int = 200) -> list[WhatsAppPilotEntitlement]:
        lim = max(1, min(int(limit or 200), 500))
        stmt = select(WhatsAppPilotEntitlement).order_by(WhatsAppPilotEntitlement.created_at.desc()).limit(lim)
        if status:
            stmt = (
                select(WhatsAppPilotEntitlement)
                .where(WhatsAppPilotEntitlement.status == status)
                .order_by(WhatsAppPilotEntitlement.created_at.desc())
                .limit(lim)
            )
        return list(self.session.scalars(stmt))

    def add_audit(
        self,
        *,
        tenant_id: str,
        event_type: str,
        detail: dict[str, Any],
        connection_id: str | None = None,
        conversation_id: str | None = None,
        actor_user_id: str | None = None,
    ) -> WhatsAppAuditEvent:
        # Never persist secrets or message bodies in audit detail.
        safe = {
            k: v
            for k, v in detail.items()
            if k
            not in {
                "access_token",
                "token",
                "code",
                "app_secret",
                "ciphertext",
                "authorization",
                "text",
                "body",
                "message_body",
            }
        }
        row = WhatsAppAuditEvent(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            connection_id=connection_id,
            conversation_id=conversation_id,
            actor_user_id=actor_user_id,
            event_type=event_type,
            detail=safe,
        )
        self.session.add(row)
        self.session.flush()
        return row
