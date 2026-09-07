"""Persist TikTok advertiser credentials and enhanced bindings. Never store media URLs."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models.tiktok_business import TikTokConnection, TikTokCredential
from db.models.tiktok_enhanced import TikTokEnhancedBinding
from services.tiktok_business.capabilities import (
    TOKEN_KIND_ADVERTISER,
    default_binding_payload,
    empty_capabilities,
)
from services.tiktok_business.crypto import open_tiktok_tokens, seal_tiktok_tokens
from services.tiktok_business.errors import TikTokOAuthStateError


def _utcnow() -> datetime:
    return datetime.now(UTC)


class TikTokEnhancedRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_binding(self, *, tenant_id: str, connection_id: str) -> TikTokEnhancedBinding | None:
        return self.session.scalar(
            select(TikTokEnhancedBinding).where(
                TikTokEnhancedBinding.tenant_id == tenant_id,
                TikTokEnhancedBinding.connection_id == connection_id,
            )
        )

    def get_or_create_binding(self, *, tenant_id: str, connection_id: str) -> TikTokEnhancedBinding:
        row = self.get_binding(tenant_id=tenant_id, connection_id=connection_id)
        if row is not None:
            if row.tenant_id != tenant_id:
                raise TikTokOAuthStateError("Enhanced binding tenant mismatch")
            return row
        defaults = default_binding_payload()
        row = TikTokEnhancedBinding(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            connection_id=connection_id,
            status=str(defaults["status"]),
            reason_code=str(defaults["reason_code"]),
            capabilities=empty_capabilities(),
        )
        self.session.add(row)
        self.session.flush()
        return row

    def store_advertiser_credential(
        self,
        *,
        connection: TikTokConnection,
        access_token: str,
        refresh_token: str,
        scopes: list[str],
        access_expires_at: datetime,
        refresh_expires_at: datetime | None,
    ) -> TikTokCredential:
        binding = self.get_or_create_binding(tenant_id=connection.tenant_id, connection_id=connection.id)
        if binding.advertiser_credential_id:
            previous = self.session.get(TikTokCredential, binding.advertiser_credential_id)
            if previous is not None:
                previous.revoked_at = _utcnow()
        cred = TikTokCredential(
            id=str(uuid.uuid4()),
            tenant_id=connection.tenant_id,
            connection_id=connection.id,
            token_kind=TOKEN_KIND_ADVERTISER,
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
        binding.advertiser_credential_id = cred.id
        if connection.credential_id == cred.id:
            raise TikTokOAuthStateError("refusing to overwrite the account-holder credential")
        return cred

    def open_advertiser_tokens(self, *, tenant_id: str, connection_id: str) -> dict[str, Any] | None:
        binding = self.get_binding(tenant_id=tenant_id, connection_id=connection_id)
        if binding is None or not binding.advertiser_credential_id:
            return None
        cred = self.session.get(TikTokCredential, binding.advertiser_credential_id)
        if cred is None or cred.revoked_at is not None:
            return None
        if cred.tenant_id != tenant_id:
            raise TikTokOAuthStateError("Advertiser credential tenant mismatch")
        if cred.token_kind != TOKEN_KIND_ADVERTISER:
            raise TikTokOAuthStateError("Stored credential is not an advertiser token")
        opened = open_tiktok_tokens(ciphertext=cred.ciphertext, tenant_id=tenant_id, connection_id=connection_id)
        opened["token_kind"] = TOKEN_KIND_ADVERTISER
        opened["credential"] = cred
        return opened

    def replace_advertiser_tokens(
        self,
        *,
        connection: TikTokConnection,
        access_token: str,
        refresh_token: str,
        scopes: list[str],
        access_expires_at: datetime,
        refresh_expires_at: datetime | None,
    ) -> TikTokCredential:
        return self.store_advertiser_credential(
            connection=connection,
            access_token=access_token,
            refresh_token=refresh_token,
            scopes=scopes,
            access_expires_at=access_expires_at,
            refresh_expires_at=refresh_expires_at,
        )

    def apply_probe(
        self,
        binding: TikTokEnhancedBinding,
        *,
        status: str,
        reason_code: str,
        capabilities: dict[str, Any],
        advertiser_id: str = "",
        bc_id: str = "",
        identity_id: str = "",
        identity_type: str = "",
        identity_authorized_bc_id: str = "",
        cooldown_until: datetime | None = None,
    ) -> None:
        if binding.tenant_id != str(binding.tenant_id):
            raise TikTokOAuthStateError("Enhanced binding tenant mismatch")
        binding.status = status
        binding.reason_code = (reason_code or "")[:64]
        binding.capabilities = dict(capabilities or empty_capabilities())
        binding.advertiser_id = (advertiser_id or "")[:64]
        binding.bc_id = (bc_id or "")[:64]
        binding.identity_id = (identity_id or "")[:128]
        binding.identity_type = (identity_type or "")[:32]
        binding.identity_authorized_bc_id = (identity_authorized_bc_id or "")[:64]
        binding.last_probe_at = _utcnow()
        binding.last_probe_code = (reason_code or "")[:64]
        binding.probe_cooldown_until = cooldown_until

    def clear_enhanced(self, *, tenant_id: str, connection_id: str) -> str:
        """Revoke advertiser credential and reset binding. Does not touch account tokens."""
        token = ""
        binding = self.get_binding(tenant_id=tenant_id, connection_id=connection_id)
        if binding is None:
            return token
        if binding.advertiser_credential_id:
            cred = self.session.get(TikTokCredential, binding.advertiser_credential_id)
            if cred is not None and cred.tenant_id == tenant_id:
                try:
                    opened = open_tiktok_tokens(
                        ciphertext=cred.ciphertext, tenant_id=tenant_id, connection_id=connection_id
                    )
                    token = str(opened.get("access_token") or "")
                except Exception:
                    token = ""
                cred.revoked_at = _utcnow()
        binding.advertiser_credential_id = None
        binding.advertiser_id = ""
        binding.bc_id = ""
        binding.identity_id = ""
        binding.identity_type = ""
        binding.identity_authorized_bc_id = ""
        binding.status = "authorization_required"
        binding.reason_code = "authorization_required"
        binding.capabilities = empty_capabilities()
        binding.last_probe_at = None
        binding.probe_cooldown_until = None
        binding.last_probe_code = ""
        return token
