"""Signed preview tokens for explicit user-confirmed Meta social publishing."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from typing import Any


class SocialPostConfirmError(ValueError):
    pass


@dataclass(frozen=True)
class SocialPostPreview:
    tenant_id: str
    actor_id: str
    facebook_binding_id: str
    instagram_binding_id: str
    caption: str
    media_id: str
    publish_facebook: bool
    publish_instagram: bool
    created_at: int
    expires_at: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "actor_id": self.actor_id,
            "facebook_binding_id": self.facebook_binding_id,
            "instagram_binding_id": self.instagram_binding_id,
            "caption": self.caption,
            "media_id": self.media_id,
            "publish_facebook": self.publish_facebook,
            "publish_instagram": self.publish_instagram,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> SocialPostPreview:
        return cls(
            tenant_id=str(payload.get("tenant_id") or ""),
            actor_id=str(payload.get("actor_id") or ""),
            facebook_binding_id=str(payload.get("facebook_binding_id") or ""),
            instagram_binding_id=str(payload.get("instagram_binding_id") or ""),
            caption=str(payload.get("caption") or ""),
            media_id=str(payload.get("media_id") or ""),
            publish_facebook=bool(payload.get("publish_facebook")),
            publish_instagram=bool(payload.get("publish_instagram")),
            created_at=int(payload.get("created_at") or 0),
            expires_at=int(payload.get("expires_at") or 0),
        )


_PREVIEW_TTL_SECONDS = 600


def _signing_secret() -> bytes:
    secret = (
        os.getenv("META_APP_A_SECRET")
        or os.getenv("META_APP_SECRET")
        or os.getenv("DASHBOARD_SESSION_SECRET")
        or ""
    ).strip()
    if not secret:
        raise SocialPostConfirmError("Social post signing secret is not configured")
    return secret.encode("utf-8")


def create_preview_token(*, preview: SocialPostPreview) -> str:
    payload_bytes = json.dumps(preview.to_dict(), separators=(",", ":"), sort_keys=True).encode("utf-8")
    digest = hmac.new(_signing_secret(), payload_bytes, hashlib.sha256).hexdigest()
    envelope = {"payload": preview.to_dict(), "sig": digest}
    return base64.urlsafe_b64encode(json.dumps(envelope, separators=(",", ":")).encode("utf-8")).decode("ascii")


def verify_preview_token(token: str) -> SocialPostPreview:
    try:
        raw = base64.urlsafe_b64decode(token.encode("ascii"))
        envelope = json.loads(raw.decode("utf-8"))
    except (ValueError, json.JSONDecodeError) as exc:
        raise SocialPostConfirmError("Invalid preview token") from exc
    if not isinstance(envelope, dict):
        raise SocialPostConfirmError("Invalid preview token envelope")
    payload = envelope.get("payload")
    received_sig = str(envelope.get("sig") or "")
    if not isinstance(payload, dict) or not received_sig:
        raise SocialPostConfirmError("Invalid preview token envelope")
    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    expected_sig = hmac.new(_signing_secret(), payload_bytes, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(received_sig, expected_sig):
        raise SocialPostConfirmError("Preview token signature mismatch")
    preview = SocialPostPreview.from_dict(payload)
    if not preview.tenant_id:
        raise SocialPostConfirmError("Preview token missing tenant")
    if preview.expires_at < int(time.time()):
        raise SocialPostConfirmError("Preview token expired")
    return preview


def build_preview(
    *,
    tenant_id: str,
    actor_id: str,
    facebook_binding_id: str,
    instagram_binding_id: str,
    caption: str,
    media_id: str,
    publish_facebook: bool,
    publish_instagram: bool,
) -> tuple[SocialPostPreview, str]:
    now = int(time.time())
    preview = SocialPostPreview(
        tenant_id=tenant_id,
        actor_id=actor_id,
        facebook_binding_id=facebook_binding_id,
        instagram_binding_id=instagram_binding_id,
        caption=caption.strip(),
        media_id=media_id,
        publish_facebook=publish_facebook,
        publish_instagram=publish_instagram,
        created_at=now,
        expires_at=now + _PREVIEW_TTL_SECONDS,
    )
    if not preview.publish_facebook and not preview.publish_instagram:
        raise SocialPostConfirmError("Select at least one platform")
    if not preview.caption:
        raise SocialPostConfirmError("Caption is required")
    if preview.publish_instagram and not preview.media_id:
        raise SocialPostConfirmError("Instagram posts require an image")
    return preview, create_preview_token(preview=preview)
