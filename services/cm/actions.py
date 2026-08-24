"""Published CM ``actions`` helpers — capability gates + Meta comment readiness."""

from __future__ import annotations

from typing import Any

from services.cm.schemas import ActionsSection
from services.cm.version_store import PublishedVersionError, load_published_content, read_published_pointer
from services.meta_app_registry import (
    META_COMMENT_SCOPES,
    MetaAppRegistry,
    MetaAssetBinding,
    MetaBindingCredential,
    MetaChannel,
)
from services.meta_graph_routing import required_comment_scopes_for_binding

ACTION_FACEBOOK_COMMENTS = "respond_facebook_comments"
ACTION_INSTAGRAM_COMMENTS = "respond_instagram_comments"
ACTION_TIKTOK_COMMENTS = "respond_tiktok_comments"
ACTION_FACEBOOK_DM = "respond_facebook_dm"
ACTION_INSTAGRAM_DM = "respond_instagram_dm"
ACTION_TIKTOK_DM = "respond_tiktok_dm"
ACTION_HUMAN_HANDOFF = "human_handoff"
ACTION_PHOTO_ANALYSIS = "photo_analysis"

_CHANNEL_COMMENT_ACTION: dict[str, str] = {
    "facebook": ACTION_FACEBOOK_COMMENTS,
    "instagram": ACTION_INSTAGRAM_COMMENTS,
    "tiktok": ACTION_TIKTOK_COMMENTS,
}


def load_actions_section(tenant_id: str) -> ActionsSection | None:
    """Return published actions for the tenant, or None when unpublished/unloadable."""
    from services.tenant_runtime_config_service import load_actions_payload, postgres_enabled

    if postgres_enabled():
        payload = load_actions_payload(tenant_id)
        if payload is not None:
            return ActionsSection.model_validate(payload)
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
    cm_action_enabled: bool,
    per_asset_switch_enabled: bool,
    binding: MetaAssetBinding | None = None,
    credential: MetaBindingCredential | None = None,
) -> dict[str, Any]:
    """Clear readiness report for comment replies (code + Meta scopes). Not a live App Review claim."""
    ch = cast_channel(channel)
    if binding is not None:
        required = set(required_comment_scopes_for_binding(binding))
    else:
        required = set(META_COMMENT_SCOPES.get(ch, frozenset()))
    granted: set[str] = set()
    permission_status = "unknown"
    permission_source = ""
    permission_verified_at = 0.0
    if binding is not None and credential is not None:
        from services.meta_comment_permission_verification import (
            comment_permission_public_snapshot,
            effective_comment_permission_status,
        )

        snapshot = comment_permission_public_snapshot(binding, credential)
        granted = set(snapshot["scopes_granted"])
        permission_status = effective_comment_permission_status(binding, credential)
        permission_source = str(snapshot.get("source") or "")
        permission_verified_at = float(snapshot.get("verified_at") or 0)
    elif credential is not None:
        granted = set(credential.scopes or ()) & required
    missing = sorted(required - granted)
    scopes_ready = permission_status == "verified_granted"
    live_ready = bool(cm_action_enabled and per_asset_switch_enabled and scopes_ready)
    return {
        "channel": ch,
        "cm_action_id": comments_action_id_for_channel(ch),
        "cm_action_enabled": bool(cm_action_enabled),
        "per_asset_switch_enabled": bool(per_asset_switch_enabled),
        "scopes_required": sorted(required),
        "scopes_granted": sorted(granted),
        "scopes_missing": missing,
        "scopes_ready": permission_status == "verified_granted" if binding and credential else not missing,
        "permission_status": permission_status,
        "permission_source": permission_source,
        "permission_verified_at": permission_verified_at,
        "code_path_ready": bool(cm_action_enabled and per_asset_switch_enabled),
        "live_reply_ready": live_ready,
        "live_verified": False,
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
    binding: MetaAssetBinding | None = None,
    credential: MetaBindingCredential | None = None,
    registry: MetaAppRegistry | None = None,
) -> dict[str, Any]:
    """Decide whether comment AI may run; always returns a structured reason."""
    from services.cm.constants import tenant_allows_legacy_bridge, tenant_uses_cm_runtime
    from services.meta_app_registry import get_meta_app_registry
    from services.meta_comment_permission_verification import (
        comment_permission_public_snapshot,
        effective_comment_permission_status,
        maybe_reconcile_binding_comment_permission,
        persist_comment_permission_from_credential,
    )

    if tenant_uses_cm_runtime(tenant_id):
        action_on = comments_action_enabled(tenant_id, channel)
    elif tenant_allows_legacy_bridge(tenant_id):
        action_on = True
    else:
        action_on = False

    resolved_binding = binding
    resolved_credential = credential
    current_registry = registry
    if resolved_binding is not None and current_registry is not None:
        fresh = next(
            (
                item
                for item in current_registry.list_bindings(include_inactive=True, include_superseded=True)
                if item.binding_id == resolved_binding.binding_id
            ),
            None,
        )
        if fresh is not None:
            resolved_binding = fresh
    if resolved_binding is not None and resolved_credential is None:
        if current_registry is None:
            current_registry = get_meta_app_registry()
        resolved_credential = current_registry.get_credential(resolved_binding)

    readiness = evaluate_comments_meta_readiness(
        channel=channel,
        cm_action_enabled=action_on,
        per_asset_switch_enabled=per_asset_enabled,
        binding=resolved_binding,
        credential=resolved_credential,
    )
    if not per_asset_enabled:
        return {"allow": False, "reason": "feature_disabled", "readiness": readiness}
    if not action_on:
        return {"allow": False, "reason": "cm_action_disabled", "readiness": readiness}
    if resolved_binding is None or resolved_credential is None:
        return {
            "allow": False,
            "reason": "comment_permissions_could_not_be_verified",
            "readiness": readiness,
        }

    permission_status = effective_comment_permission_status(resolved_binding, resolved_credential)
    if permission_status == "unknown":
        if current_registry is None:
            current_registry = get_meta_app_registry()
        try:
            resolved_binding = persist_comment_permission_from_credential(
                resolved_binding,
                resolved_credential,
                registry=current_registry,
                source="oauth_stored_scopes",
                actor_id="runtime_stored_scopes",
            )
            permission_status = effective_comment_permission_status(resolved_binding, resolved_credential)
            readiness = evaluate_comments_meta_readiness(
                channel=channel,
                cm_action_enabled=action_on,
                per_asset_switch_enabled=per_asset_enabled,
                binding=resolved_binding,
                credential=resolved_credential,
            )
        except Exception:
            permission_status = "unknown"
        if permission_status == "unknown" and maybe_reconcile_binding_comment_permission(
            resolved_binding,
            registry=current_registry,
        ):
            readiness["permission_reconcile_scheduled"] = True

    permission = comment_permission_public_snapshot(resolved_binding, resolved_credential)
    readiness["permission_status"] = permission["status"]
    readiness["permission_source"] = permission["source"]
    readiness["permission_verified_at"] = permission["verified_at"]
    readiness["scopes_ready"] = permission["status"] == "verified_granted"

    if permission["status"] == "verified_missing":
        return {"allow": False, "reason": "comment_scopes_missing", "readiness": readiness, "permission": permission}
    if permission["status"] != "verified_granted":
        return {
            "allow": False,
            "reason": "comment_permissions_could_not_be_verified",
            "readiness": readiness,
            "permission": permission,
        }
    return {"allow": True, "reason": "ok", "readiness": readiness, "permission": permission}
