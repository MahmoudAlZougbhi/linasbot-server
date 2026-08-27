"""WhatsApp Cloud PostgreSQL repository — transactional SoT operations.

Runtime mixin: repository_runtime; helpers/views: repository_helpers (LOC split).
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, timedelta
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models.whatsapp_cloud import (
    WhatsAppConnection,
    WhatsAppConnectionAttempt,
    WhatsAppCredential,
    WhatsAppOutboundIntent,
)
from services.whatsapp_cloud.config import WHATSAPP_COEXISTENCE_FEATURE
from services.whatsapp_cloud.crypto import open_whatsapp_token, seal_whatsapp_token
from services.whatsapp_cloud.repository_helpers import (
    ACTIVE_LIFECYCLES,
    _utcnow,
    connection_public_view,
    conversation_public_view,
)
from services.whatsapp_cloud.repository_runtime import WhatsAppCloudRepositoryRuntimeMixin

__all__ = [
    "ACTIVE_LIFECYCLES",
    "WhatsAppCloudRepository",
    "connection_public_view",
    "conversation_public_view",
]


class WhatsAppCloudRepository(WhatsAppCloudRepositoryRuntimeMixin):
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
            feature_type=WHATSAPP_COEXISTENCE_FEATURE,
            status="pending",
            expires_at=_utcnow() + timedelta(seconds=ttl_seconds),
        )
        self.session.add(attempt)
        self.session.flush()
        return attempt, nonce

    def get_attempt_by_state_hash(self, state_hash: str) -> Any:
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
    def find_active_by_phone_number_id(self, phone_number_id: str) -> Any:
        rows = self.session.scalars(
            select(WhatsAppConnection).where(
                WhatsAppConnection.phone_number_id == phone_number_id,
                WhatsAppConnection.lifecycle_status.in_(tuple(ACTIVE_LIFECYCLES)),
            )
        ).all()
        return rows[0] if rows else None

    def list_tenant_connections(
        self,
        tenant_id: str,
        *,
        include_revoked: bool = True,
    ) -> list[WhatsAppConnection]:
        stmt = select(WhatsAppConnection).where(WhatsAppConnection.tenant_id == tenant_id)
        if not include_revoked:
            stmt = stmt.where(WhatsAppConnection.lifecycle_status != "revoked")
        return list(self.session.scalars(stmt.order_by(WhatsAppConnection.created_at.desc())).all())

    def get_connection(self, connection_id: str) -> Any:
        return self.session.get(WhatsAppConnection, connection_id)

    def get_tenant_connection(self, *, tenant_id: str, connection_id: str) -> Any:
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
        connection_source: str = "embedded_signup",
    ) -> WhatsAppConnection:
        source = str(connection_source or "embedded_signup").strip() or "embedded_signup"
        if source not in {"embedded_signup", "meta_app_review_test"}:
            raise ValueError("invalid_connection_source")
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
            connection_source=source,
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

    def suppress_pending_outbound_for_connection(
        self,
        *,
        connection_id: str,
        tenant_id: str,
        reason: str,
    ) -> int:
        rows = list(
            self.session.scalars(
                select(WhatsAppOutboundIntent).where(
                    WhatsAppOutboundIntent.connection_id == connection_id,
                    WhatsAppOutboundIntent.tenant_id == tenant_id,
                    WhatsAppOutboundIntent.dispatch_state.in_(("pending", "sending")),
                )
            ).all()
        )
        for intent in rows:
            intent.dispatch_state = "suppressed"
            intent.error_code = reason[:64]
        self.session.flush()
        return len(rows)

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

    def rotate_connection_credential(
        self,
        conn: WhatsAppConnection,
        *,
        access_token: str,
        scopes: list[str],
        expected_generation: int,
    ) -> WhatsAppCredential:
        """Atomically switch a connected row to a new sealed credential generation."""

        expected_connection_id = conn.id
        expected_credential_id = conn.credential_id
        expected_tenant_id = conn.tenant_id
        expected_waba_id = conn.waba_id
        expected_phone_number_id = conn.phone_number_id
        expected_meta_app_id = conn.meta_app_id
        self.session.refresh(conn, with_for_update=True)
        credential = cast(
            WhatsAppCredential | None,
            self.session.get(WhatsAppCredential, conn.credential_id, with_for_update=True)
            if conn.credential_id
            else None,
        )
        if credential is None:
            raise PermissionError("credential_missing")
        if (
            conn.id != expected_connection_id
            or conn.credential_id != expected_credential_id
            or conn.tenant_id != expected_tenant_id
            or conn.waba_id != expected_waba_id
            or conn.phone_number_id != expected_phone_number_id
            or conn.meta_app_id != expected_meta_app_id
            or conn.connection_source != "meta_app_review_test"
            or conn.lifecycle_status != "connected"
            or credential.id != conn.credential_id
            or credential.tenant_id != conn.tenant_id
            or credential.connection_id != conn.id
            or credential.revoked_at is not None
        ):
            raise PermissionError("credential_rotation_state_conflict")
        if (
            int(conn.credential_generation or 0) != expected_generation
            or int(credential.generation or 0) != expected_generation
        ):
            raise PermissionError("credential_generation_conflict")
        generation = expected_generation + 1
        credential.ciphertext = seal_whatsapp_token(
            access_token=access_token,
            tenant_id=conn.tenant_id,
            connection_id=conn.id,
            scopes=scopes,
        )
        credential.generation = generation
        credential.scopes = list(scopes)
        conn.credential_generation = generation
        conn.granted_scopes = list(scopes)
        self.session.flush()
        return credential

    # --- conversations / control ---
