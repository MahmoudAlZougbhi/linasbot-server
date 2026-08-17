"""PostgreSQL repository for TikTok Business connections and credentials."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from db.models.tiktok_business import TikTokAuditEvent, TikTokConnection, TikTokCredential, TikTokOAuthAttempt
from services.tiktok_business.config import SYNC_LEASE_SECONDS
from services.tiktok_business.crypto import open_tiktok_tokens, seal_tiktok_tokens
from services.tiktok_business.errors import TikTokOAuthStateError
from services.tiktok_business.scopes import comments_status, dm_status

ACTIVE = frozenset({"connecting", "connected", "permission_required", "token_expired", "error"})


def _utcnow() -> datetime:
    return datetime.now(UTC)


class TikTokRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_attempt(
        self,
        *,
        tenant_id: str,
        actor_user_id: str,
        return_surface: str,
        state_hash: str,
        expires_at: datetime,
    ) -> TikTokOAuthAttempt:
        row = TikTokOAuthAttempt(
            id=str(uuid.uuid4()),
            state_hash=state_hash,
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            return_surface=return_surface,
            correlation_id=uuid.uuid4().hex,
            status="pending",
            expires_at=expires_at,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def consume_attempt(self, *, state_hash: str, signed_tenant_id: str) -> TikTokOAuthAttempt:
        now = _utcnow()
        stmt = (
            update(TikTokOAuthAttempt)
            .where(
                TikTokOAuthAttempt.state_hash == state_hash,
                TikTokOAuthAttempt.status == "pending",
                TikTokOAuthAttempt.expires_at > now,
                TikTokOAuthAttempt.tenant_id == signed_tenant_id,
            )
            .values(status="consumed", consumed_at=now, outcome_code="consumed")
        )
        result = self.session.execute(stmt)
        if int(result.rowcount or 0) != 1:
            existing = self.session.scalar(
                select(TikTokOAuthAttempt).where(TikTokOAuthAttempt.state_hash == state_hash)
            )
            if existing is None:
                raise TikTokOAuthStateError("OAuth state is unknown")
            if existing.tenant_id != signed_tenant_id:
                raise TikTokOAuthStateError("OAuth state tenant mismatch")
            if existing.status != "pending":
                raise TikTokOAuthStateError("OAuth state was already used")
            raise TikTokOAuthStateError("OAuth state has expired")
        row = self.session.scalar(select(TikTokOAuthAttempt).where(TikTokOAuthAttempt.state_hash == state_hash))
        if row is None:
            raise TikTokOAuthStateError("OAuth state is unknown")
        return row

    def list_tenant_connections(self, tenant_id: str, *, include_revoked: bool = False) -> list[TikTokConnection]:
        stmt = select(TikTokConnection).where(TikTokConnection.tenant_id == tenant_id)
        if not include_revoked:
            stmt = stmt.where(TikTokConnection.lifecycle_status.in_(tuple(ACTIVE)))
        return list(self.session.scalars(stmt.order_by(TikTokConnection.updated_at.desc())))

    def get_active_for_tenant(self, tenant_id: str) -> TikTokConnection | None:
        rows = self.list_tenant_connections(tenant_id)
        return rows[0] if rows else None

    def get_by_open_id_active(self, open_id: str) -> TikTokConnection | None:
        return self.session.scalar(
            select(TikTokConnection).where(
                TikTokConnection.open_id == open_id,
                TikTokConnection.lifecycle_status.in_(tuple(ACTIVE)),
            )
        )

    def get_connection(self, connection_id: str, *, tenant_id: str | None = None) -> TikTokConnection | None:
        stmt = select(TikTokConnection).where(TikTokConnection.id == connection_id)
        if tenant_id:
            stmt = stmt.where(TikTokConnection.tenant_id == tenant_id)
        return self.session.scalar(stmt)

    def upsert_connection(
        self,
        *,
        tenant_id: str,
        actor_user_id: str,
        open_id: str,
        display_name: str,
        username: str,
        avatar_url: str,
        scopes: list[str],
        access_token: str,
        refresh_token: str,
        access_expires_at: datetime,
        refresh_expires_at: datetime | None,
        lifecycle_status: str,
    ) -> TikTokConnection:
        existing_other = self.get_by_open_id_active(open_id)
        if existing_other and existing_other.tenant_id != tenant_id:
            raise PermissionError("tiktok_account_owned_by_other_tenant")
        current = self.get_active_for_tenant(tenant_id)
        if current and current.open_id != open_id:
            current.lifecycle_status = "revoked"
            current.revoked_at = _utcnow()
            current.revoked_by_user_id = actor_user_id
        connection = current if current and current.open_id == open_id else None
        if connection is None:
            connection = TikTokConnection(
                id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                created_by_user_id=actor_user_id,
                authorized_by_user_id=actor_user_id,
                open_id=open_id,
            )
            self.session.add(connection)
            self.session.flush()
        token_expired = access_expires_at <= _utcnow()
        error = lifecycle_status == "error"
        connected = lifecycle_status in {"connected", "permission_required", "token_expired"}
        connection.authorized_by_user_id = actor_user_id
        connection.display_name = display_name[:255]
        connection.username = username[:255]
        connection.avatar_url = avatar_url[:1024]
        connection.granted_scopes = list(scopes)
        connection.lifecycle_status = lifecycle_status
        connection.comments_capability = comments_status(
            granted=scopes, connected=connected, token_expired=token_expired, error=error
        )
        connection.dm_capability = dm_status(
            granted=scopes, connected=connected, token_expired=token_expired, error=error
        )
        connection.last_error = None
        self.session.flush()
        if connection.credential_id:
            previous = self.session.get(TikTokCredential, connection.credential_id)
            if previous is not None:
                previous.revoked_at = _utcnow()
        cred = TikTokCredential(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            connection_id=connection.id,
            ciphertext=seal_tiktok_tokens(
                access_token=access_token,
                refresh_token=refresh_token,
                tenant_id=tenant_id,
                connection_id=connection.id,
                scopes=list(scopes),
            ),
            scopes=list(scopes),
            access_expires_at=access_expires_at,
            refresh_expires_at=refresh_expires_at,
        )
        self.session.add(cred)
        self.session.flush()
        connection.credential_id = cred.id
        self.audit(tenant_id=tenant_id, connection_id=connection.id, actor=actor_user_id, event="connected")
        return connection

    def open_tokens(self, connection: TikTokConnection) -> dict[str, Any]:
        if not connection.credential_id:
            raise TikTokOAuthStateError("TikTok connection has no credential")
        cred = self.session.get(TikTokCredential, connection.credential_id)
        if cred is None or cred.revoked_at is not None:
            raise TikTokOAuthStateError("TikTok credential is unavailable")
        return open_tiktok_tokens(
            ciphertext=cred.ciphertext, tenant_id=connection.tenant_id, connection_id=connection.id
        )

    def replace_tokens(
        self,
        connection: TikTokConnection,
        *,
        access_token: str,
        refresh_token: str,
        scopes: list[str],
        access_expires_at: datetime,
        refresh_expires_at: datetime | None,
    ) -> None:
        if connection.credential_id:
            previous = self.session.get(TikTokCredential, connection.credential_id)
            if previous is not None:
                previous.revoked_at = _utcnow()
        cred = TikTokCredential(
            id=str(uuid.uuid4()),
            tenant_id=connection.tenant_id,
            connection_id=connection.id,
            ciphertext=seal_tiktok_tokens(
                access_token=access_token,
                refresh_token=refresh_token,
                tenant_id=connection.tenant_id,
                connection_id=connection.id,
                scopes=list(scopes),
            ),
            scopes=list(scopes),
            access_expires_at=access_expires_at,
            refresh_expires_at=refresh_expires_at,
        )
        self.session.add(cred)
        self.session.flush()
        connection.credential_id = cred.id
        connection.granted_scopes = list(scopes)
        connection.lifecycle_status = "connected"
        connection.last_error = None

    def mark_revoked(self, connection: TikTokConnection, *, actor: str, reason: str) -> None:
        connection.lifecycle_status = "revoked"
        connection.revoked_at = _utcnow()
        connection.revoked_by_user_id = actor
        connection.last_error = reason[:255]
        if connection.credential_id:
            cred = self.session.get(TikTokCredential, connection.credential_id)
            if cred is not None:
                cred.revoked_at = _utcnow()
        self.audit(tenant_id=connection.tenant_id, connection_id=connection.id, actor=actor, event="disconnected")

    def claim_sync_lease(self, connection_id: str, *, owner: str) -> TikTokConnection | None:
        now = _utcnow()
        until = now + timedelta(seconds=SYNC_LEASE_SECONDS)
        stmt = (
            update(TikTokConnection)
            .where(
                TikTokConnection.id == connection_id,
                TikTokConnection.lifecycle_status.in_(tuple(ACTIVE)),
                (TikTokConnection.sync_lease_until.is_(None) | (TikTokConnection.sync_lease_until < now)),
            )
            .values(sync_lease_until=until, sync_lease_owner=owner)
        )
        result = self.session.execute(stmt)
        if int(result.rowcount or 0) != 1:
            return None
        return self.session.get(TikTokConnection, connection_id)

    def list_due_for_sync(self, *, limit: int = 25) -> list[TikTokConnection]:
        now = _utcnow()
        stmt = (
            select(TikTokConnection)
            .where(
                TikTokConnection.lifecycle_status.in_(("connected", "permission_required")),
                (TikTokConnection.sync_lease_until.is_(None) | (TikTokConnection.sync_lease_until < now)),
            )
            .order_by(TikTokConnection.last_sync_at.asc())
            .limit(limit)
        )
        return list(self.session.scalars(stmt))

    def audit(self, *, tenant_id: str, connection_id: str | None, actor: str, event: str, detail: str = "") -> None:
        self.session.add(
            TikTokAuditEvent(
                id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                connection_id=connection_id,
                actor_user_id=actor,
                event_type=event,
                detail=detail[:255],
            )
        )
