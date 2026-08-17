"""Signed, one-time TikTok OAuth state. Tenant is never taken from the callback query."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass

from services.tiktok_business.config import OAUTH_STATE_TTL_SECONDS, require_tiktok_settings
from services.tiktok_business.errors import TikTokOAuthStateError


def _signing_key() -> bytes:
    return require_tiktok_settings().client_secret.encode("utf-8")


def _sign(message: str) -> str:
    return hmac.new(_signing_key(), message.encode("utf-8"), hashlib.sha256).hexdigest()


@dataclass(frozen=True)
class SignedOAuthState:
    nonce: str
    state_hash: str
    state: str
    expires_at_unix: int


def create_signed_state(*, tenant_id: str, actor_user_id: str, return_surface: str) -> SignedOAuthState:
    tenant = str(tenant_id or "").strip()
    actor = str(actor_user_id or "").strip()
    surface = str(return_surface or "mobile").strip().lower()
    if not tenant or not actor:
        raise TikTokOAuthStateError("OAuth state requires tenant and initiating user")
    if surface not in {"mobile", "web"}:
        surface = "web"
    nonce = secrets.token_urlsafe(32)
    expires_at = int(time.time()) + OAUTH_STATE_TTL_SECONDS
    body = f"{nonce}|{tenant}|{actor}|{surface}|{expires_at}"
    state = f"{body}.{_sign(body)}"
    state_hash = hashlib.sha256(nonce.encode("utf-8")).hexdigest()
    return SignedOAuthState(nonce=nonce, state_hash=state_hash, state=state, expires_at_unix=expires_at)


def parse_signed_state(raw: str) -> dict[str, str]:
    text = str(raw or "").strip()
    if "." not in text:
        raise TikTokOAuthStateError("OAuth state is malformed")
    body, signature = text.rsplit(".", 1)
    parts = body.split("|")
    if len(parts) != 5:
        raise TikTokOAuthStateError("OAuth state is malformed")
    nonce, tenant_id, actor_user_id, return_surface, exp_raw = parts
    if not hmac.compare_digest(_sign(body), signature):
        raise TikTokOAuthStateError("OAuth state signature is invalid")
    try:
        expires_at = int(exp_raw)
    except ValueError as exc:
        raise TikTokOAuthStateError("OAuth state expiry is invalid") from exc
    if expires_at < int(time.time()):
        raise TikTokOAuthStateError("OAuth state has expired")
    if return_surface not in {"mobile", "web"}:
        raise TikTokOAuthStateError("OAuth state return surface is invalid")
    return {
        "nonce": nonce,
        "tenant_id": tenant_id,
        "actor_user_id": actor_user_id,
        "return_surface": return_surface,
        "state_hash": hashlib.sha256(nonce.encode("utf-8")).hexdigest(),
        "expires_at": str(expires_at),
    }
