"""Published CM ``actions`` helpers — capability gates + Meta comment readiness."""

from __future__ import annotations

from typing import Any

from services.cm.schemas import ActionsSection
from services.cm.version_store import PublishedVersionError, load_published_content, read_published_pointer
from services.meta_app_registry import META_COMMENT_SCOPES, MetaChannel

ACTION_FACEBOOK_COMMENTS = "respond_facebook_comments"
ACTION_INSTAGRAM_COMMENTS = "respond_instagram_comments"
ACTION_FACEBOOK_DM = "respond_facebook_dm"
ACTION_INSTAGRAM_DM = "respond_instagram_dm"
ACTION_HUMAN_HANDOFF = "human_handoff"
ACTION_PHOTO_ANALYSIS = "photo_analysis"

_CHANNEL_COMMENT_ACTION: dict[str, str] = {
    "facebook": ACTION_FACEBOOK_COMMENTS,
    "instagram": ACTION_INSTAGRAM_COMMENTS,
}


def load_actions_section(tenant_id: str) -> ActionsSection | None:
    """Return published actions for the tenant, or None when unpublished/unloadable."""
    if read_published_pointer(tenant_id) is None:
        return None
    try:
        _pointer, sections = load_published_content(tenant_id)
    except PublishedVersionError:
        return None
    return ActionsSection.model_validate(sections.get("actions") or {})


def action_enabled(actions: ActionsSection | dict[str, Any] | None, action_id: str) -> bool:
    if actions is None:
        return False
    section = actions if isinstance(actions, ActionsSection) else ActionsSection.model_validate(actions)
    for item in section.items:
        if item.id == action_id:
            return bool(item.enabled)
    return False


def published_action_enabled(tenant_id: str, action_id: str) -> bool:
    return action_enabled(load_actions_section(tenant_id), action_id)


def comments_action_id_for_channel(channel: str) -> str | None:
    return _CHANNEL_COMMENT_ACTION.get((channel or "").strip().lower())


def comments_action_enabled(tenant_id: str, channel: str) -> bool:
    action_id = comments_action_id_for_channel(channel)
    if not action_id:
        return False
    return published_action_enabled(tenant_id, action_id)


def required_comment_scopes_for_channel(channel: MetaChannel | str) -> frozenset[str]:
    key = cast_channel(channel)
    return META_COMMENT_SCOPES.get(key, frozenset())


def cast_channel(channel: MetaChannel | str) -> MetaChannel:
    value = (channel or "").strip().lower()
    if value == "instagram":
        return "instagram"
    return "facebook"


def evaluate_comments_meta_readiness(
    *,
    channel: str,
    granted_scopes: set[str] | frozenset[str] | list[str] | None,
    cm_action_enabled: bool,
    per_asset_switch_enabled: bool,
) -> dict[str, Any]:
    """Clear readiness report for comment replies (code + Meta scopes). Not a live App Review claim."""
    ch = cast_channel(channel)
    required = set(META_COMMENT_SCOPES.get(ch, frozenset()))
    granted = set(granted_scopes or [])
    missing = sorted(required - granted)
    scopes_ready = not missing
    live_ready = bool(cm_action_enabled and per_asset_switch_enabled and scopes_ready)
    return {
        "channel": ch,
        "cm_action_id": comments_action_id_for_channel(ch),
        "cm_action_enabled": bool(cm_action_enabled),
        "per_asset_switch_enabled": bool(per_asset_switch_enabled),
        "scopes_required": sorted(required),
        "scopes_granted": sorted(required & granted),
        "scopes_missing": missing,
        "scopes_ready": scopes_ready,
        "code_path_ready": bool(cm_action_enabled and per_asset_switch_enabled),
        "live_reply_ready": live_ready,
        "live_verified": False,  # never claimed without production/App Review evidence
        "note": (
            "live_reply_ready means code + scopes + switches look sufficient locally; "
            "Meta App Review / production live comment delivery is an external verification gate."
        ),
    }


def comments_enforcement_decision(
    *,
    tenant_id: str,
    channel: str,
    per_asset_enabled: bool,
    granted_scopes: set[str] | frozenset[str] | list[str] | None = None,
) -> dict[str, Any]:
    """Decide whether comment AI may run; always returns a structured reason."""
    from services.cm.constants import tenant_allows_legacy_bridge, tenant_uses_cm_runtime

    if tenant_uses_cm_runtime(tenant_id):
        action_on = comments_action_enabled(tenant_id, channel)
    elif tenant_allows_legacy_bridge(tenant_id):
        # Temporary: linas unpublished bridge keeps per-asset toggle as the gate.
        action_on = True
    else:
        action_on = False

    readiness = evaluate_comments_meta_readiness(
        channel=channel,
        granted_scopes=granted_scopes,
        cm_action_enabled=action_on,
        per_asset_switch_enabled=per_asset_enabled,
    )
    if not per_asset_enabled:
        return {"allow": False, "reason": "feature_disabled", "readiness": readiness}
    if not action_on:
        return {"allow": False, "reason": "cm_action_disabled", "readiness": readiness}
    if granted_scopes is not None and not readiness["scopes_ready"]:
        return {"allow": False, "reason": "comment_scopes_missing", "readiness": readiness}
    return {"allow": True, "reason": "ok", "readiness": readiness}
