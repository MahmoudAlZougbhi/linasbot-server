"""Per-channel IG/FB DM + Comments status for the tenant dashboard."""

from __future__ import annotations

from typing import Any

from services.channel_capability_state import capability_state, supported_platforms
from services.integration_capabilities import list_tenant_integration_status
from services.tenant_mobile_dashboard.status import plan_comment_entitlement


def _row_for_platform(integrations: list[dict[str, Any]], platform: str) -> dict[str, Any] | None:
    for row in integrations:
        if isinstance(row, dict) and str(row.get("platform") or "").lower() == platform:
            return row
    return None


def _capability_card(
    *,
    platform: str,
    capability: str,
    state: dict[str, Any],
    membership_allows: bool,
    interactions: int | None,
) -> dict[str, Any]:
    operational = bool(state.get("effective_enabled") or state.get("live_verified"))
    connected = bool(state.get("connection_healthy")) or bool(
        # Bindings may exist even when unhealthy — connected flag comes from integration row.
        state.get("permission_present") or state.get("webhook_subscribed")
    )
    blocker_code = state.get("blocker_code")
    if capability == "comments" and not membership_allows:
        blocker_code = "plan_comments_disabled"
        operational = False
    action_code = None
    action_label = None
    if not membership_allows and capability == "comments":
        action_code, action_label = "upgrade_plan", "Upgrade"
    elif blocker_code == "connect_channel_first":
        if platform == "instagram":
            action_code = "connect_instagram"
        elif platform == "tiktok":
            action_code = "connect_tiktok"
        else:
            action_code = "connect_facebook"
        action_label = "Connect"
    elif blocker_code in {
        "missing_comment_permissions",
        "missing_dm_permissions",
        "meta_approval_required",
        "reauthorization_required",
        "connection_unhealthy",
        "tiktok_messaging_pending",
    }:
        action_code, action_label = "review_permissions", "Review permissions"
    elif not operational:
        action_code, action_label = "manage_integrations", "Manage"

    return {
        "platform": platform,
        "capability": capability,
        "connected": connected,
        "enabled": bool(state.get("requested_enabled")),
        "membership_allows": membership_allows if capability == "comments" else True,
        "permission_present": bool(state.get("permission_present")),
        "webhook_subscribed": bool(state.get("webhook_subscribed")),
        "connection_healthy": bool(state.get("connection_healthy")),
        "operational": operational and (membership_allows if capability == "comments" else True),
        "live_verified": bool(state.get("live_verified")) if capability == "dm" else False,
        "status": state.get("status"),
        "blocker_code": blocker_code,
        "blocker_message": state.get("blocker_message"),
        "interactions": interactions,
        "credits_used": None,
        "credits_used_available": False,
        "action": {"code": action_code, "label": action_label} if action_code else None,
    }


def build_channel_breakdown(
    tenant_id: str,
    *,
    features: dict[str, Any],
    usage: dict[str, Any],
) -> dict[str, Any]:
    comment_ent = plan_comment_entitlement(features)
    membership_allows = bool(comment_ent["membership_allows_comments"])
    integrations = list_tenant_integration_status(tenant_id)
    cards: list[dict[str, Any]] = []
    any_connected = False
    connection_issue = False
    dm_ok = False

    interaction_map = {
        ("instagram", "dm"): usage.get("instagram_dms"),
        ("facebook", "dm"): usage.get("facebook_dms"),
        ("instagram", "comments"): usage.get("instagram_comments"),
        ("facebook", "comments"): usage.get("facebook_comments"),
        ("tiktok", "dm"): usage.get("tiktok_dms"),
        ("tiktok", "comments"): usage.get("tiktok_comments"),
    }

    for platform in supported_platforms():
        row = _row_for_platform(integrations, platform)
        connected = bool(row and row.get("connected"))
        if connected:
            any_connected = True
        dm_state = capability_state(tenant_id, platform, "dm")
        comments_state = capability_state(tenant_id, platform, "comments")
        # Prefer integration connected flag for display when registry says connected.
        if connected:
            dm_state = {**dm_state, "connection_healthy": bool(dm_state.get("connection_healthy")) or connected}
        dm_card = _capability_card(
            platform=platform,
            capability="dm",
            state=dm_state,
            membership_allows=True,
            interactions=interaction_map.get((platform, "dm")),
        )
        comments_card = _capability_card(
            platform=platform,
            capability="comments",
            state=comments_state,
            membership_allows=membership_allows,
            interactions=interaction_map.get((platform, "comments")),
        )
        dm_card["connected"] = connected
        comments_card["connected"] = connected
        if connected and not dm_card["connection_healthy"]:
            connection_issue = True
        if dm_card["operational"]:
            dm_ok = True
        cards.append(dm_card)
        cards.append(comments_card)

    tiktok_row = _row_for_platform(integrations, "tiktok")
    if tiktok_row is not None:
        tt_connected = bool(tiktok_row.get("connected"))
        if tt_connected:
            any_connected = True
        raw_comments = tiktok_row.get("comments_state")
        raw_dm = tiktok_row.get("dm_state")
        tt_comments_state: dict[str, Any] = raw_comments if isinstance(raw_comments, dict) else {}
        tt_dm_state: dict[str, Any] = raw_dm if isinstance(raw_dm, dict) else {}
        dm_card = _capability_card(
            platform="tiktok",
            capability="dm",
            state=tt_dm_state,
            membership_allows=True,
            interactions=interaction_map.get(("tiktok", "dm")),
        )
        comments_card = _capability_card(
            platform="tiktok",
            capability="comments",
            state=tt_comments_state,
            membership_allows=membership_allows,
            interactions=interaction_map.get(("tiktok", "comments")),
        )
        dm_card["connected"] = tt_connected
        comments_card["connected"] = tt_connected
        if dm_card["operational"]:
            dm_ok = True
        cards.append(dm_card)
        cards.append(comments_card)

    return {
        "status": "ok",
        "any_connected": any_connected,
        "connection_issue": connection_issue,
        "dm_operational": dm_ok,
        "membership_allows_comments": membership_allows,
        "channels": cards,
    }
