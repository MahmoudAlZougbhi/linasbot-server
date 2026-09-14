"""Status / blocker copy for the channel capability matrix."""

from __future__ import annotations

from typing import Any, Literal

CapabilityKey = Literal["dm", "comments"]

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
    "comment_permissions_could_not_be_verified": (
        "Comment permissions could not be verified for the current token. "
        "The connection stays enabled, but AI comment replies are paused until verification succeeds."
    ),
}


def missing_comment_permissions_message(platform: str) -> str:
    if platform == "facebook":
        return BLOCKER_MESSAGES["missing_comment_permissions_facebook"]
    if platform == "instagram":
        return BLOCKER_MESSAGES["missing_comment_permissions_instagram"]
    return BLOCKER_MESSAGES["missing_comment_permissions"]


def empty_capability_state(capability: CapabilityKey, platform_key: str, checked_at: float) -> dict[str, Any]:
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


def status_and_blocker(
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
    comment_permission_statuses: list[str] | None = None,
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
        if (
            capability == "comments"
            and comment_permission_statuses
            and any(status == "unknown" for status in comment_permission_statuses)
        ):
            code = "comment_permissions_could_not_be_verified"
            return "configuring", code, BLOCKER_MESSAGES[code]
        code = "missing_comment_permissions" if capability == "comments" else "missing_dm_permissions"
        status = "permission_required" if capability == "comments" else "reauthorization_required"
        message = missing_comment_permissions_message(platform) if capability == "comments" else BLOCKER_MESSAGES[code]
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
