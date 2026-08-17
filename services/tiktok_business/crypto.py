"""Encrypt TikTok tokens at rest using the Meta AES-GCM credential cipher."""

from __future__ import annotations

import os
from typing import Any

from services.meta_app_registry import MetaCredentialCipher, MetaCredentialError, MetaRegistryNotConfiguredError


def tiktok_credential_cipher() -> MetaCredentialCipher:
    secret = (os.getenv("META_CREDENTIAL_ENCRYPTION_KEY") or "").strip()
    if len(secret) < 32:
        raise MetaRegistryNotConfiguredError("META_CREDENTIAL_ENCRYPTION_KEY must be at least 32 characters")
    return MetaCredentialCipher(secret)


def seal_tiktok_tokens(
    *,
    access_token: str,
    refresh_token: str,
    tenant_id: str,
    connection_id: str,
    scopes: list[str],
    extra: dict[str, Any] | None = None,
) -> str:
    if not str(access_token or "").strip():
        raise MetaCredentialError("refusing to seal empty TikTok access token")
    payload: dict[str, Any] = {
        "access_token": access_token.strip(),
        "refresh_token": str(refresh_token or "").strip(),
        "scopes": list(scopes),
        "channel": "tiktok",
    }
    if extra:
        payload.update({k: v for k, v in extra.items() if k not in {"access_token", "refresh_token"}})
    aad = f"tiktok:{tenant_id}:{connection_id}"
    return tiktok_credential_cipher().seal(payload, aad=aad)


def open_tiktok_tokens(*, ciphertext: str, tenant_id: str, connection_id: str) -> dict[str, Any]:
    aad = f"tiktok:{tenant_id}:{connection_id}"
    opened = tiktok_credential_cipher().open(ciphertext, aad=aad)
    token = str(opened.get("access_token") or "").strip()
    if not token:
        raise MetaCredentialError("stored TikTok credential missing access_token")
    return opened
