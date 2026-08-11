"""WhatsApp Cloud PostgreSQL repository — transactional SoT operations."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from db.models.whatsapp_cloud import (
    WhatsAppAuditEvent,
    WhatsAppConnection,
    WhatsAppConnectionAttempt,
    WhatsAppConversation,
    WhatsAppCredential,
    WhatsAppMessage,
    WhatsAppOutboundIntent,
    WhatsAppPilotEntitlement,
    WhatsAppWebhookEvent,
)
from services.whatsapp_cloud.crypto import open_whatsapp_token, seal_whatsapp_token

ACTIVE_LIFECYCLES = frozenset(
    {
        "connected",
        "provisioning",
        "syncing_history",
        "needs_attention",
        "awaiting_meta",
        "starting",
    }
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _mask_id(value: str) -> str:
    raw = str(value or "").strip()
    if len(raw) <= 6:
        return "***"
    return f"{raw[:3]}…{raw[-3:]}"


def _mask_phone_wa_id(value: str) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if len(digits) < 4:
        return "***"
    return f"***{digits[-4:]}"


class WhatsAppCloudRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    # --- attempts ---
    def create_connection_attempt(
        self,
        *,
        tenant_id: str,
        actor_user_id: str,
        return_surface: str,
        meta_app_key: str,
        ttl_seconds: int = 600,
    ) -> tuple[WhatsAppConnectionAttempt, str]:
        nonce = secrets.token_urlsafe(32)
        state_hash = hashlib.sha256(nonce.encode("utf-8")).hexdigest()
        correlation_id = uuid.uuid4().hex
        attempt = WhatsAppConnectionAttempt(
            id=str(uuid.uuid4()),
            state_hash=state_hash,
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            meta_app_key=meta_app_key,
            return_surface=return_surface,
            correlation_id=correlation_id,
            status="pending",
            expires_at=_utcnow() + timedelta(seconds=ttl_seconds),
        )
        self.session.add(attempt)
        self.session.flush()
        return attempt, nonce

    def get_attempt_by_state_hash(self, state_hash: str) -> WhatsAppConnectionAttempt | None:
        return self.session.scalar(
            select(WhatsAppConnectionAttempt).where(WhatsAppConnectionAttempt.state_hash == state_hash)
        )

    def consume_attempt(
        self,
        attempt: WhatsAppConnectionAttempt,
        *,
        outcome_code: str,
        outcome_detail: str | None = None,
        status: str = "consumed",
    ) -> WhatsAppConnectionAttempt:
        now = _utcnow()
        if attempt.status != "pending":
            raise ValueError("attempt_not_pending")
        if attempt.expires_at.replace(tzinfo=UTC) < now:
            attempt.status = "expired"
            attempt.outcome_code = "expired"
            self.session.flush()
            raise ValueError("attempt_expired")
        attempt.status = status
        attempt.consumed_at = now
        attempt.outcome_code = outcome_code
        attempt.outcome_detail = (outcome_detail or "")[:255] or None
        self.session.flush()
        return attempt

    # --- connections ---
    def find_active_by_phone_number_id(self, phone_number_id: str) -> WhatsAppConnection | None:
        rows = self.session.scalars(
            select(WhatsAppConnection).where(
                WhatsAppConnection.phone_number_id == phone_number_id,
                WhatsAppConnection.lifecycle_status.in_(tuple(ACTIVE_LIFECYCLES)),
            )
        ).all()
        return rows[0] if rows else None

    def list_tenant_connections(self, tenant_id: str) -> list[WhatsAppConnection]:
        return list(
            self.session.scalars(
                select(WhatsAppConnection)
                .where(WhatsAppConnection.tenant_id == tenant_id)
                .order_by(WhatsAppConnection.created_at.desc())
            ).all()
        )

    def get_connection(self, connection_id: str) -> WhatsAppConnection | None:
        return self.session.get(WhatsAppConnection, connection_id)

    def get_tenant_connection(self, *, tenant_id: str, connection_id: str) -> WhatsAppConnection | None:
        conn = self.get_connection(connection_id)
        if conn is None or conn.tenant_id != tenant_id:
            return None
        return conn

    def create_connection_with_credential(
        self,
        *,
        tenant_id: str,
        created_by_user_id: str,
        meta_app_key: str,
        meta_app_id: str,
        waba_id: str,
        phone_number_id: str,
        display_phone_number: str,
        verified_name: str,
        access_token: str,
        scopes: list[str],
        previous_connection_id: str | None = None,
    ) -> WhatsAppConnection:
        existing = self.find_active_by_phone_number_id(phone_number_id)
        if existing is not None and existing.tenant_id != tenant_id:
            raise PermissionError("phone_number_owned_by_other_tenant")
        if existing is not None and existing.tenant_id == tenant_id and existing.lifecycle_status == "connected":
            # Preserve healthy connection until replacement fully commits — mark as previous.
            previous_connection_id = existing.id

        last4 = "".join(ch for ch in display_phone_number if ch.isdigit())[-4:]
        conn = WhatsAppConnection(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            created_by_user_id=created_by_user_id,
            meta_app_key=meta_app_key,
            meta_app_id=meta_app_id,
            waba_id=waba_id,
            phone_number_id=phone_number_id,
            display_phone_number=display_phone_number,
            display_phone_last4=last4,
            verified_name=verified_name or "",
            coexistence_mode="whatsapp_business_app_onboarding",
            lifecycle_status="provisioning",
            granted_scopes=list(scopes),
            previous_connection_id=previous_connection_id,
            ai_default_enabled=False,
            history_sync_status="pending",
        )
        self.session.add(conn)
        self.session.flush()

        ciphertext = seal_whatsapp_token(
            access_token=access_token,
            tenant_id=tenant_id,
            connection_id=conn.id,
            scopes=scopes,
        )
        cred = WhatsAppCredential(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            connection_id=conn.id,
            generation=1,
            ciphertext=ciphertext,
            scopes=list(scopes),
            token_type="user",
        )
        self.session.add(cred)
        self.session.flush()
        conn.credential_id = cred.id
        conn.credential_generation = 1

        if previous_connection_id:
            prev = self.get_connection(previous_connection_id)
            if prev is not None and prev.tenant_id == tenant_id:
                # Do not destroy previous until new connection reaches connected.
                prev.superseded_by_connection_id = conn.id
        self.session.flush()
        return conn

    def mark_connection_connected(
        self,
        conn: WhatsAppConnection,
        *,
        webhook_fields: list[str],
    ) -> WhatsAppConnection:
        conn.lifecycle_status = "connected"
        conn.webhook_subscription_status = "ready"
        conn.webhook_subscribed_fields = list(webhook_fields)
        conn.webhook_last_success_at = _utcnow()
        conn.health_status = "healthy"
        conn.health_detail = None
        if conn.previous_connection_id:
            prev = self.get_connection(conn.previous_connection_id)
            if prev is not None and prev.tenant_id == conn.tenant_id and prev.id != conn.id:
                prev.lifecycle_status = "revoked"
                prev.revoked_at = _utcnow()
                prev.revoked_reason = "superseded_by_reconnect"
        self.session.flush()
        return conn

    def revoke_connection(
        self,
        conn: WhatsAppConnection,
        *,
        actor_user_id: str,
        reason: str,
    ) -> WhatsAppConnection:
        conn.lifecycle_status = "revoked"
        conn.revoked_at = _utcnow()
        conn.revoked_by_user_id = actor_user_id
        conn.revoked_reason = reason[:255]
        if conn.credential_id:
            cred = self.session.get(WhatsAppCredential, conn.credential_id)
            if cred is not None:
                cred.revoked_at = _utcnow()
        self.session.flush()
        return conn

    def load_access_token(self, conn: WhatsAppConnection) -> str:
        if not conn.credential_id:
            raise PermissionError("credential_missing")
        cred = self.session.get(WhatsAppCredential, conn.credential_id)
        if cred is None or cred.revoked_at is not None:
            raise PermissionError("credential_revoked")
        opened = open_whatsapp_token(
            ciphertext=cred.ciphertext,
            tenant_id=conn.tenant_id,
            connection_id=conn.id,
        )
        return str(opened["access_token"])

    # --- conversations / control ---
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

    def get_tenant_conversation(
        self, *, tenant_id: str, conversation_id: str
    ) -> WhatsAppConversation | None:
        conv = self.session.get(WhatsAppConversation, conversation_id)
        if conv is None or conv.tenant_id != tenant_id:
            return None
        return conv

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
        existing = self.session.scalar(
            select(WhatsAppWebhookEvent).where(WhatsAppWebhookEvent.event_key == event_key)
        )
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


def connection_public_view(
    conn: WhatsAppConnection,
    *,
    ai_eligible: bool,
    rollout_blocked_reason: str | None = None,
) -> dict[str, Any]:
    from services.whatsapp_cloud.types import ConnectionPublicView

    view = ConnectionPublicView(
        connection_id=conn.id,
        tenant_id=conn.tenant_id,
        lifecycle_status=conn.lifecycle_status,  # type: ignore[arg-type]
        coexistence_mode=conn.coexistence_mode,
        display_phone_last4=conn.display_phone_last4,
        verified_name=conn.verified_name,
        waba_id_masked=_mask_id(conn.waba_id),
        phone_number_id_masked=_mask_id(conn.phone_number_id),
        webhook_subscription_status=conn.webhook_subscription_status,
        health_status=conn.health_status,
        health_detail=conn.health_detail,
        ai_eligible=ai_eligible,
        ai_default_enabled=bool(conn.ai_default_enabled),
        history_sync_status=conn.history_sync_status,
        granted_scopes=list(conn.granted_scopes or []),
        rollout_blocked_reason=rollout_blocked_reason,
    )
    return view.to_dict()


def conversation_public_view(conv: WhatsAppConversation) -> dict[str, Any]:
    from services.whatsapp_cloud.types import ConversationPublicView

    view = ConversationPublicView(
        conversation_id=conv.id,
        connection_id=conv.connection_id,
        control_state=conv.control_state,  # type: ignore[arg-type]
        control_epoch=int(conv.control_epoch),
        pause_reason=conv.pause_reason,
        customer_wa_id_masked=_mask_phone_wa_id(conv.customer_wa_id),
    )
    return view.to_dict()
