"""Safe OAuth completion redirects for Meta Business Login / Instagram Login.

Only an allowlisted ``return_surface`` stored in one-time OAuth state is honored.
Never accept an arbitrary return URL from the client.
"""

from __future__ import annotations

import hashlib
from typing import Any, Literal
from urllib.parse import urlencode

from services.meta_app_registry import MetaAppRegistry, MetaOAuthStateError, get_meta_app_registry

ReturnSurface = Literal["web", "mobile"]

MOBILE_INTEGRATIONS_DEEP_LINK = "linasai://integrations"
ALLOWED_RETURN_SURFACES = frozenset({"web", "mobile"})
_MOBILE_META_CONNECTION_VALUES = frozenset({"success", "cancelled", "failed"})


def normalize_return_surface(value: Any) -> ReturnSurface:
    """Accept only ``mobile`` or ``web``; anything else (incl. tampered) → ``web``."""

    raw = str(value or "").strip().lower()
    if raw == "mobile":
        return "mobile"
    return "web"


def mobile_meta_connection_status(meta_connection: str) -> str:
    """Map server connection outcomes to deep-link-safe status values."""

    raw = str(meta_connection or "").strip().lower()
    if raw in {"connected", "success"}:
        return "success"
    if raw in {"cancelled", "canceled"}:
        return "cancelled"
    return "failed"


def oauth_completion_redirect_url(
    *,
    return_surface: ReturnSurface | str,
    meta_connection: str,
    extra_query: dict[str, str] | None = None,
) -> str:
    """Build the post-callback redirect. Mobile never lands on ``/settings`` or ``/login``."""

    surface = normalize_return_surface(return_surface)
    if surface == "mobile":
        status = mobile_meta_connection_status(meta_connection)
        if status not in _MOBILE_META_CONNECTION_VALUES:
            status = "failed"
        # Deep link carries only a coarse status — no tokens, tenant IDs, or Meta secrets.
        return f"{MOBILE_INTEGRATIONS_DEEP_LINK}?{urlencode({'meta_connection': status})}"

    query: dict[str, str] = {"meta_connection": str(meta_connection or "failed")}
    for key, value in (extra_query or {}).items():
        if key in {"meta_connection", "access_token", "token", "tenant_id", "code", "state"}:
            continue
        text = str(value or "").strip()
        if text:
            query[key] = text
    return f"/settings?{urlencode(query)}"


def consume_return_surface_from_state(
    state: str,
    *,
    registry: MetaAppRegistry | None = None,
) -> ReturnSurface:
    """Best-effort consume leftover OAuth state on cancel/error to learn return_surface."""

    nonce = str(state or "").strip()
    if not nonce:
        return "web"
    current = registry or get_meta_app_registry()
    try:
        state_hash = hashlib.sha256(nonce.encode("utf-8")).hexdigest()
        payload = current.consume_oauth_state(state_hash)
    except MetaOAuthStateError:
        return "web"
    except Exception:
        return "web"
    return normalize_return_surface(payload.get("return_surface"))
