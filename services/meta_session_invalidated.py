"""Detect Meta password/session invalidation (Graph 190) and disconnect the binding."""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from services.channel_capability_state import canonical_channel_bindings
from services.meta_app_registry import APP_A_KEY, get_meta_app_registry, get_meta_graph_api_version
from services.meta_app_registry_session import PASSWORD_CHANGED_RECONNECT
from services.meta_graph_routing import graph_api_url
from services.meta_instagram_login_config import instagram_login_graph_api_version

_logger = logging.getLogger("uvicorn.error")
_CODE_RE = re.compile(r"\bcode=(\d+)\b")
_SESSION_MARKERS = (
    "session has been invalidated",
    "changed their password",
    "changed the session for security",
    "user has changed the password",
    "user changed their password",
)


def is_meta_session_invalidated(
    error: BaseException | None = None,
    *,
    http_status: int | None = None,
    error_code: Any = None,
    error_text: str = "",
) -> bool:
    """True when Meta invalidated the token (password change or security session reset)."""

    text = str(error_text or "")
    code = _as_code(error_code)
    if error is not None:
        text = f"{text} {error}".strip()
        if http_status is None:
            raw_status = getattr(error, "http_status", None)
            if isinstance(raw_status, int):
                http_status = raw_status
        if not code:
            code = _as_code(getattr(error, "error_code", None))
        if not code:
            match = _CODE_RE.search(str(error))
            if match:
                code = match.group(1)
    if code == "190":
        return True
    low = text.lower()
    if any(marker in low for marker in _SESSION_MARKERS):
        return True
    _ = http_status
    return False


def mark_if_session_invalidated(
    error: BaseException | None = None,
    *,
    binding_id: str,
    registry: Any | None = None,
    http_status: int | None = None,
    error_code: Any = None,
    error_text: str = "",
) -> bool:
    """Disconnect the binding when the error is a Meta session invalidation. Never logs tokens."""

    if not is_meta_session_invalidated(
        error,
        http_status=http_status,
        error_code=error_code,
        error_text=error_text,
    ):
        return False
    bid = str(binding_id or "").strip()
    if not bid:
        return False
    try:
        current = registry or get_meta_app_registry()
        current.mark_binding_session_invalidated(bid)
        _logger.warning("[meta-session] binding_disconnected reason=password_changed binding=%s", bid[-8:])
        return True
    except Exception:
        _logger.warning("[meta-session] mark_failed binding=%s", bid[-8:])
        return False


def latest_password_changed_binding(tenant_id: str, platform: str, *, registry: Any | None = None) -> Any | None:
    """Latest App A binding for this tenant+channel marked password_changed_reconnect."""

    tenant = str(tenant_id or "").strip().lower()
    platform_key = str(platform or "").strip().lower()
    if not tenant or platform_key not in {"instagram", "facebook"}:
        return None
    current = registry or get_meta_app_registry()
    matches: list[Any] = []
    for binding in current.list_bindings(include_inactive=True, include_superseded=True):
        if str(getattr(binding, "tenant_id", "") or "").strip().lower() != tenant:
            continue
        if str(getattr(binding, "channel", "") or "") != platform_key:
            continue
        if str(getattr(binding, "app_key", "") or "") != APP_A_KEY:
            continue
        if str(getattr(binding, "webhook_subscription_error", "") or "") != PASSWORD_CHANGED_RECONNECT:
            continue
        matches.append(binding)
    if not matches:
        return None
    return sorted(
        matches,
        key=lambda item: (
            float(getattr(item, "updated_at", 0) or 0),
            float(getattr(item, "created_at", 0) or 0),
            str(getattr(item, "binding_id", "") or ""),
        ),
        reverse=True,
    )[0]


async def probe_binding_session(binding: Any, *, registry: Any, client: httpx.AsyncClient | None = None) -> bool:
    """GET /me for one active binding. Marks disconnected only on session invalidation."""

    try:
        credential = registry.get_credential(binding)
        token = str(getattr(credential, "access_token", "") or "").strip()
    except Exception:
        return False
    if not token:
        return False
    auth_flow = str(getattr(binding, "auth_flow", "") or "")
    version = instagram_login_graph_api_version() if auth_flow == "instagram_login" else get_meta_graph_api_version()
    url = graph_api_url(binding, graph_api_version=version, path="me")
    owns_client = client is None
    http_client = client or httpx.AsyncClient(timeout=8.0)
    try:
        response = await http_client.get(
            url,
            params={"fields": "id"},
            headers={"Authorization": f"Bearer {token}"},
        )
    except httpx.HTTPError:
        return False
    finally:
        if owns_client:
            await http_client.aclose()
    code, message = _graph_error_from_response(response)
    return mark_if_session_invalidated(
        http_status=int(response.status_code),
        error_code=code,
        error_text=message,
        binding_id=str(getattr(binding, "binding_id", "") or ""),
        registry=registry,
    )


async def probe_tenant_meta_sessions(
    tenant_id: str,
    *,
    registry: Any | None = None,
    client: httpx.AsyncClient | None = None,
) -> int:
    """Best-effort session check for active Instagram/Facebook bindings. Returns marked count."""

    current = registry or get_meta_app_registry()
    marked = 0
    for platform in ("instagram", "facebook"):
        for binding in canonical_channel_bindings(tenant_id, platform):
            if await probe_binding_session(binding, registry=current, client=client):
                marked += 1
    return marked


def _as_code(value: Any) -> str:
    if value is None or value == "" or value == "unknown":
        return ""
    return str(value).strip()


def _graph_error_from_response(response: httpx.Response) -> tuple[str, str]:
    try:
        payload = response.json()
    except (TypeError, ValueError):
        return "", ""
    if not isinstance(payload, dict):
        return "", ""
    error = payload.get("error")
    if isinstance(error, dict):
        return str(error.get("code") or "").strip(), str(error.get("message") or "")
    return str(payload.get("code") or "").strip(), str(payload.get("error_message") or payload.get("message") or "")
