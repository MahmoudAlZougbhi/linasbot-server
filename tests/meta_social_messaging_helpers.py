"""Shared helpers for Meta social messaging tests."""

from __future__ import annotations

import hashlib
import hmac


def _sign(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _social_user_data(
    channel: str = "instagram",
    *,
    sender: str = "social-sender-a",
    tenant: str = "linas",
    account: str | None = None,
) -> dict:
    asset_id = account or ("17841413184256533" if channel == "instagram" else "378696005334409")
    return {
        "tenant_id": tenant,
        "channel": channel,
        "meta_account_id": asset_id,
        "social_sender_id": sender,
    }
