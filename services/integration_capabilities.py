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
    "dm_read": _cap(level="unavailable", supported_in_code=False),
    "dm_reply": _cap(level="unavailable", supported_in_code=False),
    "comment_read": _cap(level="coming_later", supported_in_code=False),
    "comment_reply": _cap(level="coming_later", supported_in_code=False),
    "content_publish": _cap(level="coming_later", supported_in_code=False),
    "reel_publish": _cap(level="coming_later", supported_in_code=False),
    "analytics": _cap(level="coming_later", supported_in_code=False),
    "webhooks": _cap(level="coming_later", supported_in_code=False),
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


def list_tenant_integration_status(tenant_id: str) -> list[dict[str, Any]]:
    connected = False
    granted: list[str] = []
    try:
        from services.meta_app_registry import get_meta_app_registry

        registry = get_meta_app_registry()
        bindings = [
            b
            for b in registry.list_bindings(include_inactive=False, include_superseded=False)
            if getattr(b, "tenant_id", None) == tenant_id
        ]
        connected = bool(bindings)
        for b in bindings:
            scopes = getattr(b, "granted_scopes", None) or ()
            granted.extend(str(s) for s in scopes)
    except Exception:
        connected = False

    meta_caps = _meta_base()
    scope_set = {str(s) for s in granted}
    if connected:
        for key in ("dm_read", "dm_reply", "webhooks"):
            meta_caps[key]["level"] = "connected"
            meta_caps[key]["permission_present"] = True
            # live_verified remains true only for existing DM path that is already in production.
            meta_caps[key]["live_verified"] = True
        if "instagram_manage_comments" in scope_set or "pages_manage_engagement" in scope_set:
            meta_caps["comment_read"]["permission_present"] = True
            meta_caps["comment_read"]["level"] = "needs_permission"
            meta_caps["comment_read"]["live_verified"] = False
            meta_caps["comment_reply"]["permission_present"] = True
            meta_caps["comment_reply"]["live_verified"] = False
        if "instagram_content_publish" in scope_set or "pages_manage_posts" in scope_set:
            meta_caps["content_publish"]["permission_present"] = True
            meta_caps["content_publish"]["level"] = "needs_permission"
            meta_caps["content_publish"]["live_verified"] = False
            meta_caps["content_publish"]["app_review_advanced_access"] = False

    return [
        {
            "platform": "meta",
            "label": "Facebook / Instagram",
            "connected": connected,
            "capabilities": meta_caps,
            "granted_scopes": sorted(set(granted)),
        },
        {
            "platform": "tiktok",
            "label": "TikTok",
            "connected": False,
            "capabilities": {k: dict(v) for k, v in TIKTOK_CAPABILITIES.items()},
            "audit_notes": "Official API capability audit pending Meta stability.",
        },
        {
            "platform": "snapchat",
            "label": "Snapchat",
            "connected": False,
            "capabilities": {k: dict(v) for k, v in SNAP_CAPABILITIES.items()},
            "audit_notes": "Official API capability audit pending Meta stability.",
        },
    ]
