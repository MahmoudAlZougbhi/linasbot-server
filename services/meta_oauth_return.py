"""Safe OAuth completion redirects for Meta Business Login / Instagram Login.

Only an allowlisted ``return_surface`` stored in one-time OAuth state is honored.
Never accept an arbitrary return URL from the client.

Mobile returns to the Linas AI app via ``linasai://integrations``.
Web returns to the public marketing landing — never Operator ``/login`` or ``/settings``.
"""

from __future__ import annotations

import hashlib
import html
import json
from typing import Any, Literal
from urllib.parse import urlencode

from fastapi.responses import HTMLResponse, RedirectResponse

from services.meta_app_registry import MetaAppRegistry, MetaOAuthStateError, get_meta_app_registry

ReturnSurface = Literal["web", "mobile"]

MOBILE_INTEGRATIONS_DEEP_LINK = "linasai://integrations"
# Public marketing site only — do not send OAuth completions into the ops SPA.
WEB_OAUTH_COMPLETION_PATH = "/"
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
    """Build the post-callback redirect target.

    Mobile never lands on ``/settings`` or ``/login``.
    Web never lands on the Operator SPA — only the public landing page.
    """

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
    return f"{WEB_OAUTH_COMPLETION_PATH}?{urlencode(query)}"


def oauth_completion_response(
    *,
    return_surface: ReturnSurface | str,
    meta_connection: str,
    extra_query: dict[str, str] | None = None,
) -> RedirectResponse | HTMLResponse:
    """HTTP response after OAuth callback.

    Mobile uses a tiny HTML bridge so Meta's in-app browser opens ``linasai://``
    reliably (bare 303 to a custom scheme is often ignored).
    """

    target = oauth_completion_redirect_url(
        return_surface=return_surface,
        meta_connection=meta_connection,
        extra_query=extra_query,
    )
    surface = normalize_return_surface(return_surface)
    if surface != "mobile":
        return RedirectResponse(url=target, status_code=303)

    safe_href = html.escape(target, quote=True)
    safe_js = json.dumps(target)
    status = mobile_meta_connection_status(meta_connection)
    body = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <meta name="robots" content="noindex,nofollow"/>
  <meta http-equiv="refresh" content="0;url={safe_href}"/>
  <title>Return to Linas AI</title>
  <style>
    body {{ font-family: system-ui, -apple-system, sans-serif; margin: 2rem; color: #171A19; }}
    a {{ color: #06715F; font-weight: 600; }}
  </style>
</head>
<body>
  <h1>Opening Linas AI…</h1>
  <p>Facebook connection status: <strong>{html.escape(status)}</strong>.</p>
  <p>If the app does not open automatically, tap below.</p>
  <p><a href="{safe_href}">Open Linas AI</a></p>
  <p>You can close this browser tab after the app opens.</p>
  <script>
    (function () {{
      var target = {safe_js};
      try {{ window.location.replace(target); }} catch (e) {{}}
      setTimeout(function () {{
        try {{ window.location.href = target; }} catch (e) {{}}
      }}, 250);
    }})();
  </script>
</body>
</html>
"""
    return HTMLResponse(
        content=body,
        status_code=200,
        headers={"X-Robots-Tag": "noindex, nofollow"},
    )


def attach_return_surface(exc: BaseException, return_surface: ReturnSurface | str) -> None:
    """Preserve OAuth return_surface on errors after one-time state was consumed."""

    try:
        target: Any = exc
        target.return_surface = normalize_return_surface(return_surface)
    except Exception:
        return


def peek_return_surface_from_state(
    state: str,
    *,
    registry: MetaAppRegistry | None = None,
) -> ReturnSurface:
    """Read return_surface from OAuth state without consuming the one-time nonce."""

    nonce = str(state or "").strip()
    if not nonce:
        return "web"
    current = registry or get_meta_app_registry()
    try:
        state_hash = hashlib.sha256(nonce.encode("utf-8")).hexdigest()
        payload = current.peek_oauth_state(state_hash)
    except MetaOAuthStateError:
        return "web"
    except Exception:
        return "web"
    return normalize_return_surface(payload.get("return_surface"))


def resolve_error_return_surface(
    exc: BaseException | None,
    state: str,
    *,
    peeked: ReturnSurface | None = None,
    registry: MetaAppRegistry | None = None,
) -> ReturnSurface:
    """Prefer peeked surface, then exception attribute, then leftover OAuth state."""

    if peeked in ALLOWED_RETURN_SURFACES:
        return normalize_return_surface(peeked)
    attached = getattr(exc, "return_surface", None) if exc is not None else None
    if attached in ALLOWED_RETURN_SURFACES:
        return normalize_return_surface(attached)
    return consume_return_surface_from_state(state, registry=registry)


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
