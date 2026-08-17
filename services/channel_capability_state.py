"""Canonical per-tenant / platform capability matrix for DMs and Comments.

Truth fields (never claim live_verified for Comments without full E2E proof):

``effective_enabled = connection_healthy AND requested_enabled AND permission_present
                      AND webhook_subscribed AND tenant_action_enabled AND comments_policy_ok``
"""

from __future__ import annotations

import os
import time
from typing import Any, Literal

from services.cm.actions import (
    ACTION_FACEBOOK_COMMENTS,
    ACTION_FACEBOOK_DM,
    ACTION_INSTAGRAM_COMMENTS,
    ACTION_INSTAGRAM_DM,
    ACTION_TIKTOK_COMMENTS,
    ACTION_TIKTOK_DM,
    action_enabled,
    load_actions_section,
)
from services.meta_app_registry import (
    APP_A_KEY,
    META_CHANNEL_SCOPES,
    get_meta_app_configs,
    get_meta_app_registry,
)
from services.meta_comment_reply_settings import get_comment_reply_setting
from services.meta_graph_routing import required_comment_scopes_for_binding
from services.meta_instagram_login_subscription import COMMENTS_SUBSCRIPTION_FIELD

ChannelPlatform = Literal["instagram", "facebook"]
CapabilityKey = Literal["dm", "comments"]

# Internal App Role / Standard Access testing only — never a global Advanced Access bypass.
INTERNAL_STANDARD_ACCESS_TENANTS = frozenset({"linas"})

_CHANNEL_ACTION_IDS: dict[str, dict[str, str]] = {
    "instagram": {"dm": ACTION_INSTAGRAM_DM, "comments": ACTION_INSTAGRAM_COMMENTS},
    "facebook": {"dm": ACTION_FACEBOOK_DM, "comments": ACTION_FACEBOOK_COMMENTS},
    "tiktok": {"dm": ACTION_TIKTOK_DM, "comments": ACTION_TIKTOK_COMMENTS},
}

_DM_WEBHOOK_FIELDS = frozenset({"messages", "messaging_postbacks"})

BLOCKER_MESSAGES: dict[str, str] = {
    "connect_channel_first": "Connect this channel before enabling the capability.",
    "missing_comment_permissions_facebook": (
        "Missing Facebook Page comment permissions on this token "
        "(pages_read_user_content, pages_manage_engagement). Disconnect this channel, "
        "then Connect again to grant comment scopes."
    ),
    "missing_comment_permissions_instagram": (
        "Missing Instagram comment permissions on this token. Disconnect Instagram, "
        "then Connect Instagram again to grant comment scopes."
    ),
    "missing_comment_permissions": (
        "Missing Meta comment permissions on this token. Disconnect this channel, then Connect again."
    ),
    "missing_dm_permissions": ("Missing Meta messaging permissions. Disconnect this channel, then Connect again."),
    "missing_comment_webhook": "Comment webhook subscription is not confirmed yet for this connection.",
    "missing_dm_webhook": "Messaging webhook subscription is not confirmed yet for this connection.",
    "meta_approval_required": (
        "Meta App Review Advanced Access is required for this capability. "
        "Complete App Review for this app and permission set, then Disconnect and Connect again."
    ),
    "reauthorization_required": (
        "This connection needs a fresh authorization. Disconnect this channel, then Connect again."
    ),
    "connection_unhealthy": (
        "Connection is not healthy (token missing or expired). Disconnect this channel, then Connect again."
    ),
    "asset_action_off": "Channel action is on but the per-asset reply switch is still off.",
    "plan_comments_disabled": (
        "Comment automation is not included on your current plan. Upgrade from Lite to Starter or higher."
    ),
}


def supported_platforms() -> tuple[str, ...]:
    return ("instagram", "facebook")


def action_id_for(platform: str, toggle: CapabilityKey) -> str | None:
    return _CHANNEL_ACTION_IDS.get(platform, {}).get(toggle)


def uses_internal_standard_access(tenant_id: str) -> bool:
    """True only for allowlisted internal tenants (App Role / Standard Access testing)."""

    return str(tenant_id or "").strip().lower() in INTERNAL_STANDARD_ACCESS_TENANTS


def comments_policy_allows(tenant_id: str, *, advanced_access: bool) -> bool:
    """Public customers stay blocked until Advanced Access; linas may use Standard Access."""

    if advanced_access:
        return True
    return uses_internal_standard_access(tenant_id)


def active_channel_bindings(tenant_id: str, platform: str) -> list[Any]:
    """All active App A bindings for this tenant+platform (may include legacy siblings)."""

    registry = get_meta_app_registry()
    return [
        b
        for b in registry.list_bindings(include_inactive=False, include_superseded=False)
        if getattr(b, "tenant_id", None) == tenant_id
        and str(getattr(b, "channel", "") or "") == platform
        and str(getattr(b, "status", "") or "") == "active"
        and str(getattr(b, "app_key", "") or "") == APP_A_KEY
    ]


def _binding_sort_key(binding: Any) -> tuple[float, float, str]:
    updated = float(getattr(binding, "updated_at", 0) or 0)
    created = float(getattr(binding, "created_at", 0) or 0)
    binding_id = str(getattr(binding, "binding_id", "") or "")
    return (updated, created, binding_id)


def _pick_preferred_binding(candidates: list[Any]) -> Any:
    return sorted(candidates, key=_binding_sort_key, reverse=True)[0]


def canonical_channel_bindings(tenant_id: str, platform: str) -> list[Any]:
    """Select one canonical binding per asset for capability evaluation.

    Instagram: prefer an active ``instagram_login`` binding for the same asset when
    present; do not AND permissions with a legacy ``facebook_login`` sibling.
    Facebook: use the active Page binding for that asset.
    Never combine different tenants, assets, or Meta apps. Does not delete legacy rows.
    """

    platform_key = (platform or "").strip().lower()
    tenant = str(tenant_id or "").strip()
    bindings = active_channel_bindings(tenant, platform_key)
    by_asset: dict[str, list[Any]] = {}
    for binding in bindings:
        # Defense in depth — never mix tenants/apps even if a caller bypasses filters.
        if str(getattr(binding, "tenant_id", "") or "") != tenant:
            continue
        if str(getattr(binding, "app_key", "") or "") != APP_A_KEY:
            continue
        if str(getattr(binding, "channel", "") or "") != platform_key:
            continue
        asset_id = str(getattr(binding, "asset_id", "") or "").strip()
        if not asset_id:
            continue
        by_asset.setdefault(asset_id, []).append(binding)

    selected: list[Any] = []
    for asset_id in sorted(by_asset.keys()):
        group = by_asset[asset_id]
        if platform_key == "instagram":
            ig_login = [b for b in group if str(getattr(b, "auth_flow", "") or "") == "instagram_login"]
            chosen = _pick_preferred_binding(ig_login) if ig_login else _pick_preferred_binding(group)
        else:
            chosen = _pick_preferred_binding(group)
        selected.append(chosen)
    return selected


def _action_requested(tenant_id: str, platform: str, toggle: CapabilityKey) -> bool:
    actions = load_actions_section(tenant_id)
    action_id = action_id_for(platform, toggle)
    if not action_id:
        return False
    return action_enabled(actions, action_id)


def _advanced_access_approved() -> bool:
    try:
        return bool(get_meta_app_configs()[APP_A_KEY].advanced_access_approved)
    except Exception:
        return False


def _instagram_login_advanced_access_approved() -> bool:
    """Return only the dedicated Instagram app's App Review decision."""

    return (os.getenv("META_INSTAGRAM_LOGIN_ADVANCED_ACCESS_APPROVED") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def binding_advanced_access_approved(binding: Any) -> bool:
    """Return the approval flag for exactly this binding's OAuth/signing app."""

    if str(getattr(binding, "auth_flow", "") or "") == "instagram_login":
        return _instagram_login_advanced_access_approved()
    return _advanced_access_approved()


def _advanced_access_for_bindings(bindings: list[Any]) -> tuple[bool, str]:
    """Require approval from the signing/OAuth domain used by every binding."""

    if not bindings:
        return False, "unresolved"
    domains = {
        "instagram_login" if str(getattr(binding, "auth_flow", "") or "") == "instagram_login" else "app_a"
        for binding in bindings
    }
    approved = all(binding_advanced_access_approved(binding) for binding in bindings)
    return approved, next(iter(domains)) if len(domains) == 1 else "mixed"


def _binding_connection_healthy(binding: Any, *, registry: Any) -> bool:
    if str(getattr(binding, "status", "") or "") != "active":
        return False
    if str(getattr(binding, "app_key", "") or "") != APP_A_KEY:
        return False
    try:
        credential = registry.get_credential(binding)
    except Exception:
        return False
    token = str(getattr(credential, "access_token", "") or "").strip()
    if not token:
        return False
    expires_at = getattr(credential, "expires_at", None)
    if expires_at is not None and int(expires_at) <= int(time.time()):
        return False
    return True


def _missing_scopes_for_capability(
    bindings: list[Any],
    *,
    registry: Any,
    capability: CapabilityKey,
) -> list[str]:
    missing: set[str] = set()
    for binding in bindings:
        channel = str(getattr(binding, "channel", "") or "")
        if capability == "comments":
            required = set(required_comment_scopes_for_binding(binding))
        elif str(getattr(binding, "auth_flow", "") or "") == "instagram_login":
            required = {"instagram_business_basic", "instagram_business_manage_messages"}
        elif channel == "instagram":
            required = set(META_CHANNEL_SCOPES["instagram"])
        else:
            required = set(META_CHANNEL_SCOPES["facebook"])
        try:
            credential = registry.get_credential(binding)
            granted = set(credential.scopes or ())
        except Exception:
            missing |= required
            continue
        missing |= required - granted
    return sorted(missing)


def _comment_webhook_subscribed(binding: Any) -> bool:
    fields = {str(item).strip().lower() for item in (getattr(binding, "webhook_subscribed_fields", ()) or ())}
    channel = str(getattr(binding, "channel", "") or "")
    auth_flow = str(getattr(binding, "auth_flow", "") or "")
    if channel == "facebook":
        return "feed" in fields
    if channel == "instagram" and auth_flow == "instagram_login":
        return COMMENTS_SUBSCRIPTION_FIELD in fields
    return COMMENTS_SUBSCRIPTION_FIELD in fields


def _dm_webhook_subscribed(binding: Any) -> bool:
    fields = {str(item).strip().lower() for item in (getattr(binding, "webhook_subscribed_fields", ()) or ())}
    # Production DM path may have empty recorded fields while Meta subscription still works.
    # Prefer explicit record when present; otherwise treat active App A messaging binding as subscribed.
    if fields:
        return _DM_WEBHOOK_FIELDS.issubset(fields)
    return str(getattr(binding, "status", "") or "") == "active"


def _tenant_comment_assets_enabled(tenant_id: str, bindings: list[Any]) -> bool:
    if not bindings:
        return False
    for binding in bindings:
        setting = get_comment_reply_setting(
            tenant_id=tenant_id,
            app_key=binding.app_key,
            channel=binding.channel,
            asset_id=binding.asset_id,
        )
        if not setting.enabled:
            return False
    return True


def _missing_comment_permissions_message(platform: str) -> str:
    if platform == "facebook":
        return BLOCKER_MESSAGES["missing_comment_permissions_facebook"]
    if platform == "instagram":
        return BLOCKER_MESSAGES["missing_comment_permissions_instagram"]
    return BLOCKER_MESSAGES["missing_comment_permissions"]


def _status_and_blocker(
    *,
    capability: CapabilityKey,
    platform: str,
    bindings: list[Any],
    requested_enabled: bool,
    permission_present: bool,
    webhook_subscribed: bool,
    tenant_action_enabled: bool,
    connection_healthy: bool,
    effective_enabled: bool,
    live_verified: bool,
    comments_policy_ok: bool,
    missing_scopes: list[str],
) -> tuple[str, str | None, str | None]:
    """Return (status, blocker_code, blocker_message)."""

    if live_verified and effective_enabled:
        return "live_verified", None, None
    if effective_enabled:
        return "enabled", None, None
    if not bindings:
        code = "connect_channel_first"
        return "disabled", code, BLOCKER_MESSAGES[code]
    if not connection_healthy:
        code = "connection_unhealthy"
        return "reauthorization_required", code, BLOCKER_MESSAGES[code]
    if not comments_policy_ok:
        # Public / non–App-Role tenants stay blocked until this app's Advanced Access.
        code = "meta_approval_required"
        return "meta_approval_required", code, BLOCKER_MESSAGES[code]
    if not permission_present:
        # Internal Standard Access (linas) with real missing scopes — never pretend Meta approval
        # is the issue, and never fabricate permissions.
        code = "missing_comment_permissions" if capability == "comments" else "missing_dm_permissions"
        status = "permission_required" if capability == "comments" else "reauthorization_required"
        message = _missing_comment_permissions_message(platform) if capability == "comments" else BLOCKER_MESSAGES[code]
        return status, code, message
    if not webhook_subscribed:
        code = "missing_comment_webhook" if capability == "comments" else "missing_dm_webhook"
        return "webhook_setup_required", code, BLOCKER_MESSAGES[code]
    if requested_enabled and not tenant_action_enabled:
        code = "asset_action_off"
        return "configuring", code, BLOCKER_MESSAGES[code]
    if permission_present and webhook_subscribed and connection_healthy and not requested_enabled:
        if capability == "comments" and not comments_policy_ok:
            code = "meta_approval_required"
            return "meta_approval_required", code, BLOCKER_MESSAGES[code]
        return "ready", None, None
    if requested_enabled and not effective_enabled:
        return "error", "capability_incomplete", "Capability is requested but not fully ready yet."
    return "disabled", None, None


def capability_state(tenant_id: str, platform: str, capability: CapabilityKey) -> dict[str, Any]:
    """Canonical capability matrix for one platform capability."""

    platform_key = (platform or "").strip().lower()
    checked_at = time.time()
    if platform_key not in _CHANNEL_ACTION_IDS:
        return {
            "capability": capability,
            "platform": platform_key,
            "requested_enabled": False,
            "permission_present": False,
            "webhook_subscribed": False,
            "tenant_action_enabled": False,
            "connection_healthy": False,
            "effective_enabled": False,
            "live_verified": False,
            "blocker_code": "connect_channel_first",
            "blocker_message": BLOCKER_MESSAGES["connect_channel_first"],
            "blocker": "connect_channel_first",
            "status": "disabled",
            "missing_scopes": [],
            "last_checked_at": checked_at,
            "app_review": {
                "advanced_access_approved": False,
                "approval_domain": "unresolved",
                "scopes_required": [],
                "scopes_missing": [],
                "live_verified": False,
            },
        }

    bindings = canonical_channel_bindings(tenant_id, platform_key)
    registry = get_meta_app_registry()
    requested_enabled = _action_requested(tenant_id, platform_key, capability)
    missing_scopes = (
        _missing_scopes_for_capability(bindings, registry=registry, capability=capability) if bindings else []
    )
    permission_present = bool(bindings) and not missing_scopes
    connection_healthy = bool(bindings) and all(_binding_connection_healthy(b, registry=registry) for b in bindings)
    advanced_access, approval_domain = _advanced_access_for_bindings(bindings)
    comments_policy_ok = comments_policy_allows(tenant_id, advanced_access=advanced_access)

    if capability == "comments":
        webhook_subscribed = bool(bindings) and all(_comment_webhook_subscribed(b) for b in bindings)
        tenant_action_enabled = _tenant_comment_assets_enabled(tenant_id, bindings) if bindings else False
        # Comments never claim live_verified without real public E2E proof.
        live_verified = False
        scopes_required = sorted(
            {scope for binding in bindings for scope in required_comment_scopes_for_binding(binding)}
        )
    else:
        webhook_subscribed = bool(bindings) and all(_dm_webhook_subscribed(b) for b in bindings)
        # DMs have no separate per-asset switch — CM action is the tenant action.
        tenant_action_enabled = bool(requested_enabled)
        # Existing production DMs are live when gates pass.
        live_verified = bool(
            connection_healthy
            and permission_present
            and webhook_subscribed
            and requested_enabled
            and comments_policy_ok
        )
        scopes_required = sorted(
            {
                scope
                for binding in bindings
                for scope in (
                    {"instagram_business_basic", "instagram_business_manage_messages"}
                    if str(getattr(binding, "auth_flow", "") or "") == "instagram_login"
                    else (
                        META_CHANNEL_SCOPES["instagram"]
                        if str(getattr(binding, "channel", "") or "") == "instagram"
                        else META_CHANNEL_SCOPES["facebook"]
                    )
                )
            }
        )

    usable_permissions = bool(permission_present and comments_policy_ok)
    effective_enabled = bool(
        connection_healthy and requested_enabled and usable_permissions and webhook_subscribed and tenant_action_enabled
    )

    status, blocker_code, blocker_message = _status_and_blocker(
        capability=capability,
        platform=platform_key,
        bindings=bindings,
        requested_enabled=requested_enabled,
        permission_present=permission_present,
        webhook_subscribed=webhook_subscribed,
        tenant_action_enabled=tenant_action_enabled,
        connection_healthy=connection_healthy,
        effective_enabled=effective_enabled,
        live_verified=live_verified,
        comments_policy_ok=comments_policy_ok,
        missing_scopes=missing_scopes,
    )

    return {
        "capability": capability,
        "platform": platform_key,
        "requested_enabled": bool(requested_enabled),
        "permission_present": bool(permission_present),
        "webhook_subscribed": bool(webhook_subscribed),
        "tenant_action_enabled": bool(tenant_action_enabled),
        "connection_healthy": bool(connection_healthy),
        "effective_enabled": effective_enabled,
        "live_verified": bool(live_verified),
        "blocker_code": blocker_code,
        "blocker_message": blocker_message,
        # Back-compat for PR #159 mobile clients.
        "blocker": blocker_code,
        "status": status,
        "missing_scopes": missing_scopes,
        "last_checked_at": checked_at,
        "app_review": {
            "advanced_access_approved": advanced_access,
            "approval_domain": approval_domain,
            "scopes_required": scopes_required,
            "scopes_missing": missing_scopes,
            "live_verified": bool(live_verified) if capability == "dm" else False,
        },
    }


def comment_capability_state(tenant_id: str, platform: str) -> dict[str, Any]:
    return capability_state(tenant_id, platform, "comments")


def dm_capability_state(tenant_id: str, platform: str) -> dict[str, Any]:
    return capability_state(tenant_id, platform, "dm")
