"""Safe display enrichment for mobile integrations API (no tokens / asset ids)."""

from __future__ import annotations

from typing import Any, Literal

from services.channel_capability_state import _binding_connection_healthy, canonical_channel_bindings
from services.meta_app_registry import get_meta_app_registry

ConnectionDisplayStatus = Literal["disconnected", "connected", "needs_reconnect", "error"]

_RECONNECT_BLOCKERS = frozenset(
    {
        "reauthorization_required",
        "connection_unhealthy",
        "missing_dm_permissions",
    }
)

_MOBILE_STRIP_KEYS = frozenset(
    {
        "binding_ids",
        "granted_scopes",
        "capabilities",
        "audit_notes",
    }
)


def _last_synced_at(binding: Any) -> float | None:
    updated = float(getattr(binding, "updated_at", 0) or 0)
    checked = float(getattr(binding, "webhook_subscription_checked_at", 0) or 0)
    ts = max(updated, checked)
    return ts if ts > 0 else None


def _binding_account_display(binding: Any, platform: str, *, registry: Any) -> dict[str, Any]:
    platform_key = (platform or "").strip().lower()
    healthy = _binding_connection_healthy(binding, registry=registry)
    status = str(getattr(binding, "status", "") or "")
    if status != "active":
        connection_status: ConnectionDisplayStatus = "needs_reconnect"
    elif healthy:
        connection_status = "connected"
    else:
        connection_status = "needs_reconnect"

    if platform_key == "facebook":
        display_name = str(getattr(binding, "page_name", "") or "").strip() or "Facebook Page"
        username = None
    else:
        username = str(getattr(binding, "instagram_username", "") or "").strip() or None
        display_name = f"@{username}" if username else "Instagram"

    return {
        "display_name": display_name,
        "username": username,
        "profile_image_url": None,
        "connection_status": connection_status,
        "last_synced_at": _last_synced_at(binding),
    }


def _overall_connection_status(
    *,
    connected: bool,
    accounts: list[dict[str, Any]],
    dm_state: dict[str, Any] | None,
    comments_state: dict[str, Any] | None,
) -> ConnectionDisplayStatus:
    if not connected:
        return "disconnected"

    statuses = {str(item.get("connection_status") or "") for item in accounts}
    if statuses and statuses == {"connected"}:
        base: ConnectionDisplayStatus = "connected"
    elif any(s == "needs_reconnect" for s in statuses):
        base = "needs_reconnect"
    else:
        base = "error"

    for state in (dm_state, comments_state):
        if not isinstance(state, dict):
            continue
        blocker = str(state.get("blocker_code") or state.get("blocker") or "")
        if blocker in _RECONNECT_BLOCKERS:
            return "needs_reconnect"
        if not bool(state.get("connection_healthy", True)) and blocker:
            return "needs_reconnect"
        if blocker and blocker not in {"connect_channel_first", "meta_approval_required", "plan_comments_disabled"}:
            if blocker in {"missing_comment_webhook", "asset_action_off"}:
                continue
            if base == "connected":
                base = "error"

    if not bool(dm_state.get("connection_healthy", True)) if isinstance(dm_state, dict) else False:
        return "needs_reconnect"
    return base


def enrich_mobile_integration_row(row: dict[str, Any], *, tenant_id: str) -> dict[str, Any]:
    """Add safe account display fields and strip technical ids from a mobile integration row."""

    platform = str(row.get("platform") or "").strip().lower()
    if platform not in {"instagram", "facebook"}:
        cleaned = {k: v for k, v in row.items() if k not in _MOBILE_STRIP_KEYS}
        if cleaned.get("account") is None:
            cleaned.pop("account", None)
        return cleaned

    canonical = canonical_channel_bindings(tenant_id, platform)
    accounts: list[dict[str, Any]] = []
    if canonical:
        registry = get_meta_app_registry()
        accounts = [_binding_account_display(binding, platform, registry=registry) for binding in canonical]

    dm_state = row.get("dm_state") if isinstance(row.get("dm_state"), dict) else None
    comments_state = row.get("comments_state") if isinstance(row.get("comments_state"), dict) else None
    toggles_raw = row.get("toggles")
    toggles: dict[str, Any] = toggles_raw if isinstance(toggles_raw, dict) else {}
    connected = bool(row.get("connected"))

    connection_status = _overall_connection_status(
        connected=connected,
        accounts=accounts,
        dm_state=dm_state,
        comments_state=comments_state,
    )
    last_synced_at: float | None = None
    for account in accounts:
        ts = account.get("last_synced_at")
        if isinstance(ts, (int, float)) and ts > 0:
            last_synced_at = max(last_synced_at or 0, float(ts))

    primary = accounts[0] if accounts else None
    cleaned = {k: v for k, v in row.items() if k not in _MOBILE_STRIP_KEYS}
    cleaned["connection_status"] = connection_status
    cleaned["last_synced_at"] = last_synced_at
    cleaned["accounts"] = accounts
    if primary:
        cleaned["account"] = primary
    cleaned["features"] = {
        "dm_replies": bool(toggles.get("dm")),
        "comment_replies": bool(toggles.get("comments")),
    }
    if canonical:
        try:
            from services.meta_app_registry import diagnose_active_meta_binding

            diagnostics = [
                reason for binding in canonical if (reason := diagnose_active_meta_binding(registry, binding))
            ]
            if diagnostics:
                cleaned["service_diagnostic"] = diagnostics[0]
        except Exception:
            pass
    return cleaned


def enrich_mobile_integration_rows(rows: list[dict[str, Any]], *, tenant_id: str) -> list[dict[str, Any]]:
    return [enrich_mobile_integration_row(row, tenant_id=tenant_id) for row in rows]


def bindings_for_disconnect(
    tenant_id: str,
    platform: str,
    *,
    asset_id: str = "",
    registry: Any | None = None,
) -> list[Any]:
    """Every unsettled binding inside one tenant+channel boundary.

    Unlike capability display, disconnect must not collapse direct Instagram and
    Page-linked Instagram siblings.  It also includes inactive/testing history so
    credentials cannot remain hidden after an explicit owner disconnect. A
    disconnected row is retried when its credential metadata is still live.
    """

    tenant = str(tenant_id or "").strip().lower()
    platform_key = (platform or "").strip().lower()
    asset = str(asset_id or "").strip()
    current_registry = registry or get_meta_app_registry()
    matches = []
    for binding in current_registry.list_bindings(include_inactive=True, include_superseded=True):
        if binding.tenant_id != tenant or binding.channel != platform_key or (asset and binding.asset_id != asset):
            continue
        if binding.status != "disconnected" or current_registry.binding_credential_is_available(binding.binding_id):
            matches.append(binding)
    return sorted(
        matches,
        key=lambda item: (
            item.asset_id,
            0 if item.active else 1,
            0 if item.auth_flow == "instagram_login" else 1,
            item.created_at,
            item.binding_id,
        ),
    )


def active_bindings_for_disconnect(tenant_id: str, platform: str) -> list[Any]:
    """Backward-compatible alias for the complete disconnect target set."""

    return bindings_for_disconnect(tenant_id, platform)
