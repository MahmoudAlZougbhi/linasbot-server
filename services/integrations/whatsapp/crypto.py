"""Credential encryption for WhatsApp Cloud tokens — reuses Meta AES-GCM primitive."""

from __future__ import annotations

import os
from typing import Any

from services.meta_app_registry import MetaCredentialCipher, MetaCredentialError, MetaRegistryNotConfiguredError


def whatsapp_credential_cipher() -> MetaCredentialCipher:
    secret = (os.getenv("META_CREDENTIAL_ENCRYPTION_KEY") or "").strip()
    if len(secret) < 32:
        raise MetaRegistryNotConfiguredError("META_CREDENTIAL_ENCRYPTION_KEY must be at least 32 characters")
    return MetaCredentialCipher(secret)


def seal_whatsapp_token(
    *,
    access_token: str,
    tenant_id: str,
    connection_id: str,
    scopes: list[str],
    extra: dict[str, Any] | None = None,
) -> str:
    if not access_token or not access_token.strip():
        raise MetaCredentialError("refusing to seal empty WhatsApp access token")
    payload: dict[str, Any] = {
        "access_token": access_token.strip(),
        "scopes": list(scopes),
        "channel": "whatsapp",
    }
    if extra:
        # Never allow caller to override access_token via extra.
        safe = {k: v for k, v in extra.items() if k != "access_token"}
        payload.update(safe)
    aad = f"whatsapp:{tenant_id}:{connection_id}"
    return whatsapp_credential_cipher().seal(payload, aad=aad)


def open_whatsapp_token(*, ciphertext: str, tenant_id: str, connection_id: str) -> dict[str, Any]:
    aad = f"whatsapp:{tenant_id}:{connection_id}"
    opened = whatsapp_credential_cipher().open(ciphertext, aad=aad)
    token = str(opened.get("access_token") or "").strip()
    if not token:
        raise MetaCredentialError("stored WhatsApp credential missing access_token")
    return opened
