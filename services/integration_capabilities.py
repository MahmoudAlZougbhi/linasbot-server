"""Platform connector capability matrix (Meta first; TikTok/Snap audited later)."""

from __future__ import annotations

from typing import Any, Literal

CapabilityLevel = Literal["available", "connected", "needs_permission", "coming_later", "unavailable"]


def _cap(
    *,
    level: CapabilityLevel,
    supported_in_code: bool,
    permission_present: bool = False,
    app_review_advanced_access: bool = False,
    webhook_active: bool = False,
    live_verified: bool = False,
    notes: str = "",
) -> dict[str, Any]:
    return {
        "level": level,
        "supported_in_code": supported_in_code,
        "permission_present": permission_present,
        "app_review_advanced_access": app_review_advanced_access,
        "webhook_active": webhook_active,
        "live_verified": live_verified,
        "notes": notes,
    }


def _meta_base() -> dict[str, dict[str, Any]]:
    return {
        "dm_read": _cap(
            level="available",
            supported_in_code=True,
            webhook_active=True,
            notes="Existing Linas Meta DM inbound path",
        ),
        "dm_reply": _cap(
            level="available",
            supported_in_code=True,
            webhook_active=True,
            notes="Existing Linas Meta DM reply path",
        ),
        "comment_read": _cap(
            level="needs_permission",
            supported_in_code=True,
            live_verified=False,
            notes="Code present; keep disabled until App Review + live_verified",
        ),
        "comment_reply": _cap(
            level="needs_permission",
            supported_in_code=True,
            live_verified=False,
            notes="Code present; keep disabled until App Review + live_verified",
        ),
        "content_publish": _cap(
            level="needs_permission",
            supported_in_code=True,
            live_verified=False,
            notes="Social posts product-gated; not live_verified",
        ),
        "reel_publish": _cap(
            level="needs_permission",
            supported_in_code=True,
            live_verified=False,
        ),
        "analytics": _cap(level="coming_later", supported_in_code=False),
        "webhooks": _cap(
            level="available",
            supported_in_code=True,
            webhook_active=True,
            notes="Preserve existing Meta webhook subscriptions",
        ),
    }


TIKTOK_CAPABILITIES: dict[str, dict[str, Any]] = {
    "dm_read": _cap(
        level="needs_permission",
        supported_in_code=True,
        notes="Business Messaging is capability-gated until TikTok product approval.",
    ),
    "dm_reply": _cap(
        level="needs_permission",
        supported_in_code=True,
        notes="Not requested in OAuth; Permission pending until message scopes exist.",
    ),
    "comment_read": _cap(level="available", supported_in_code=True, notes="Get Account Comment"),
    "comment_reply": _cap(level="available", supported_in_code=True, notes="Manage Account Comment"),
    "content_publish": _cap(level="coming_later", supported_in_code=False),
    "reel_publish": _cap(level="coming_later", supported_in_code=False),
    "analytics": _cap(level="available", supported_in_code=True, notes="Stored TikTok comment/DM metrics only"),
    "webhooks": _cap(level="available", supported_in_code=True, notes="Messaging webhooks when approved"),
}

SNAP_CAPABILITIES: dict[str, dict[str, Any]] = {
    "dm_read": _cap(level="unavailable", supported_in_code=False),
    "dm_reply": _cap(level="unavailable", supported_in_code=False),
    "comment_read": _cap(level="coming_later", supported_in_code=False),
    "comment_reply": _cap(level="coming_later", supported_in_code=False),
    "content_publish": _cap(level="coming_later", supported_in_code=False),
    "reel_publish": _cap(level="coming_later", supported_in_code=False),
    "analytics": _cap(level="coming_later", supported_in_code=False),
    "webhooks": _cap(level="coming_later", supported_in_code=False),
}


# Flat level map for load sims / legacy callers (truthful matrix is list_tenant_integration_status).
META_CAPABILITIES: dict[str, CapabilityLevel] = {key: val["level"] for key, val in _meta_base().items()}

_META_CHANNELS = ("instagram", "facebook")


def _apply_connection_to_caps(
    *,
    connected: bool,
    granted_scopes: set[str],
    channel: str,
) -> dict[str, dict[str, Any]]:
    """Build capability matrix for one Meta brand channel (internal; not primary mobile UI)."""
    meta_caps = _meta_base()
    if not connected:
        return meta_caps

    for key in ("dm_read", "dm_reply", "webhooks"):
        meta_caps[key]["level"] = "connected"
        meta_caps[key]["permission_present"] = True
        # live_verified remains true only for existing DM path that is already in production.
        meta_caps[key]["live_verified"] = True

    comment_scopes = (
        {"instagram_manage_comments", "instagram_business_manage_comments"}
        if channel == "instagram"
        else {"pages_manage_engagement", "pages_read_user_content"}
    )
    publish_scopes = {"instagram_content_publish"} if channel == "instagram" else {"pages_manage_posts"}

    if granted_scopes & comment_scopes:
        meta_caps["comment_read"]["permission_present"] = True
        meta_caps["comment_read"]["level"] = "needs_permission"
        meta_caps["comment_read"]["live_verified"] = False
        meta_caps["comment_reply"]["permission_present"] = True
        meta_caps["comment_reply"]["live_verified"] = False
    if granted_scopes & publish_scopes:
        meta_caps["content_publish"]["permission_present"] = True
        meta_caps["content_publish"]["level"] = "needs_permission"
        meta_caps["content_publish"]["live_verified"] = False
        meta_caps["content_publish"]["app_review_advanced_access"] = False
    return meta_caps


def _tenant_meta_bindings(tenant_id: str) -> tuple[list[Any], dict[str, set[str]]]:
    """Return active bindings + per-channel granted scopes for a tenant."""
    bindings: list[Any] = []
    granted_by_channel: dict[str, set[str]] = {ch: set() for ch in _META_CHANNELS}
    try:
        from services.meta_app_registry import get_meta_app_registry

        registry = get_meta_app_registry()
        bindings = [
            b
            for b in registry.list_bindings(include_inactive=False, include_superseded=False)
            if str(getattr(b, "tenant_id", "") or "").strip().lower() == str(tenant_id or "").strip().lower()
        ]
        for b in bindings:
            channel = str(getattr(b, "channel", "") or "")
            if channel not in granted_by_channel:
                continue
            scopes = getattr(b, "granted_scopes", None) or ()
            if scopes:
                granted_by_channel[channel].update(str(s) for s in scopes)
                continue
            try:
                credential = registry.get_credential(b)
                granted_by_channel[channel].update(str(s) for s in (credential.scopes or ()))
            except Exception:
                continue
    except Exception:
        return [], {ch: set() for ch in _META_CHANNELS}
    return bindings, granted_by_channel


def list_tenant_integration_status(tenant_id: str) -> list[dict[str, Any]]:
    """Per-brand integration rows with truthful connection state.

    Primary UI should only surface connected | not_connected | coming_soon.
    Capability matrix remains for internal/owner-AI consumers — do not dump it in mobile UI.
    """
    bindings, granted_by_channel = _tenant_meta_bindings(tenant_id)
    by_channel: dict[str, list[Any]] = {ch: [] for ch in _META_CHANNELS}
    for b in bindings:
        channel = str(getattr(b, "channel", "") or "")
        if channel in by_channel:
            by_channel[channel].append(b)

    rows: list[dict[str, Any]] = []
    for platform, label in (("instagram", "Instagram"), ("facebook", "Facebook")):
        channel_bindings = by_channel[platform]
        connected = bool(channel_bindings)
        binding_ids = [
            str(getattr(b, "binding_id", "") or "") for b in channel_bindings if getattr(b, "binding_id", None)
        ]
        rows.append(
            {
                "platform": platform,
                "label": label,
                "connected": connected,
                "coming_soon": False,
                "connectable": True,
                "binding_ids": binding_ids,
                "capabilities": _apply_connection_to_caps(
                    connected=connected,
                    granted_scopes=granted_by_channel[platform],
                    channel=platform,
                ),
                "granted_scopes": sorted(granted_by_channel[platform]),
            }
        )

    # WhatsApp Cloud coexistence — server-proven status only (never client-simulated Connected).
    wa_row: dict[str, Any] = {
        "platform": "whatsapp",
        "label": "WhatsApp",
        "connected": False,
        "coming_soon": False,
        "awaiting_meta_approval": True,
        "connectable": False,
        "binding_ids": [],
        "capabilities": {
            "dm_read": _cap(level="unavailable", supported_in_code=True, notes="Cloud coexistence"),
            "dm_reply": _cap(level="unavailable", supported_in_code=True, notes="Cloud coexistence"),
        },
        "lifecycle_status": "disconnected",
        "whatsapp": None,
    }
    try:
        from db.session import whatsapp_db_configured, whatsapp_session
        from services.whatsapp_cloud.config import get_whatsapp_cloud_flags
        from services.whatsapp_cloud.entitlement import assert_whatsapp_connection_allowed, connection_status_payload
        from services.whatsapp_cloud.repository import WhatsAppCloudRepository

        flags = get_whatsapp_cloud_flags()
        ui_open = bool(flags.connection_ui_enabled or flags.public_availability)
        wa_row["awaiting_meta_approval"] = not flags.public_availability
        wa_row["coming_soon"] = False
        if whatsapp_db_configured():
            with whatsapp_session() as session:
                repo = WhatsAppCloudRepository(session)
                try:
                    assert_whatsapp_connection_allowed(session, tenant_id)
                    wa_row["connectable"] = bool(ui_open)
                    wa_row["awaiting_meta_approval"] = False
                except Exception:
                    wa_row["connectable"] = False
                    wa_row["awaiting_meta_approval"] = not flags.public_availability
                connections = [
                    c
                    for c in repo.list_tenant_connections(tenant_id)
                    if c.lifecycle_status not in {"revoked", "disconnected", "failed"}
                ]
                if connections:
                    primary = connections[0]
                    payload = connection_status_payload(session, primary)
                    wa_row["connected"] = primary.lifecycle_status == "connected"
                    wa_row["lifecycle_status"] = primary.lifecycle_status
                    wa_row["binding_ids"] = [primary.id]
                    wa_row["whatsapp"] = payload
                    wa_row["coming_soon"] = False
                    wa_row["connectable"] = True
                    wa_row["awaiting_meta_approval"] = False
                    for key in ("dm_read", "dm_reply"):
                        wa_row["capabilities"][key]["level"] = "connected" if wa_row["connected"] else "available"
                        wa_row["capabilities"][key]["permission_present"] = wa_row["connected"]
                        wa_row["capabilities"][key]["supported_in_code"] = True
    except Exception:
        pass
    rows.insert(2, wa_row)

    try:
        from services.web_chat.store import web_chat_store

        web_widget = web_chat_store.get_or_create_widget(tenant_id)
        web_connected = web_widget.connected
        web_row: dict[str, Any] = {
            "platform": "web",
            "label": "Website",
            "connected": web_connected,
            "coming_soon": False,
            "connectable": True,
            "binding_ids": [],
            "capabilities": {
                "dm_read": _cap(
                    level="connected" if web_connected else "available",
                    supported_in_code=True,
                    permission_present=web_connected,
                    live_verified=web_connected,
                    notes="Tenant website chat widget",
                ),
                "dm_reply": _cap(
                    level="connected" if web_connected else "available",
                    supported_in_code=True,
                    permission_present=web_connected,
                    live_verified=web_connected,
                    notes="AI replies on embedded website chat",
                ),
            },
            "site_url": web_widget.site_url,
            "widget_key": web_widget.widget_key,
            "enabled": web_widget.enabled,
        }
    except Exception:
        web_row = {
            "platform": "web",
            "label": "Website",
            "connected": False,
            "coming_soon": False,
            "connectable": True,
            "binding_ids": [],
            "capabilities": {
                "dm_read": _cap(level="available", supported_in_code=True),
                "dm_reply": _cap(level="available", supported_in_code=True),
            },
        }

    rows.extend(
        [
            web_row,
            tiktok_row_for_tenant(tenant_id),
            {
                "platform": "snapchat",
                "label": "Snapchat",
                "connected": False,
                "coming_soon": True,
                "connectable": False,
                "binding_ids": [],
                "capabilities": {k: dict(v) for k, v in SNAP_CAPABILITIES.items()},
                "audit_notes": "Official API capability audit pending Meta stability.",
            },
        ]
    )
    return rows


def tiktok_row_for_tenant(tenant_id: str) -> dict[str, Any]:
    from services.tiktok_business.status import tiktok_integration_row

    return tiktok_integration_row(tenant_id)
