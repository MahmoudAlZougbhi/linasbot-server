"""Per-channel DM/comment enable flags for Linas AI Integrations.

Mirrors the web Content Management → Actions switches
(``respond_{facebook|instagram}_{dm|comments}``) and, for comments, also syncs
the per-asset Meta comment-reply setting used at runtime.

Comments expose separate truth fields:
``requested_enabled``, ``permission_present``, ``webhook_subscribed``, ``live_verified``.
The mobile toggle uses ``effective_enabled`` only (never a false ON when scopes are missing).
"""

from __future__ import annotations

import time
from typing import Any, Literal

from services.cm.actions import (
    ACTION_FACEBOOK_COMMENTS,
    ACTION_FACEBOOK_DM,
    ACTION_INSTAGRAM_COMMENTS,
    ACTION_INSTAGRAM_DM,
    action_enabled,
    load_actions_section,
)
from services.cm.publish import PublishBlockedError, publish_draft_sections
from services.cm.publish_gate import PublishDisabledError, ensure_publish_enabled
from services.cm.schemas import ActionCapability, ActionsSection
from services.cm.storage import ConflictError, get_draft, put_draft
from services.cm.version_store import read_published_pointer
from services.meta_app_registry import APP_A_KEY, get_meta_app_registry
from services.meta_comment_reply_settings import get_comment_reply_setting, set_comment_reply_setting
from services.meta_comment_webhooks import (
    ensure_instagram_comment_app_webhook,
    ensure_page_comment_webhook_subscription,
)
from services.meta_graph_routing import credential_has_comment_scopes, required_comment_scopes_for_binding
from services.meta_instagram_login_subscription import COMMENTS_SUBSCRIPTION_FIELD
from services.meta_oauth import MetaOAuthError

ChannelPlatform = Literal["instagram", "facebook"]
ToggleKey = Literal["dm", "comments"]

_CHANNEL_ACTION_IDS: dict[str, dict[str, str]] = {
    "instagram": {"dm": ACTION_INSTAGRAM_DM, "comments": ACTION_INSTAGRAM_COMMENTS},
    "facebook": {"dm": ACTION_FACEBOOK_DM, "comments": ACTION_FACEBOOK_COMMENTS},
}

_COMMENT_SCOPES_MISSING_MESSAGE = (
    "Missing Meta comment permissions. Use Manage permissions / Reauthorize with comment access "
    "for the same Facebook Page / Instagram account (do not Disconnect)."
)


class ChannelToggleError(Exception):
    def __init__(self, message: str, *, status_code: int = 400, code: str = "TOGGLE_ERROR") -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


def supported_platforms() -> tuple[str, ...]:
    return ("instagram", "facebook")


def action_id_for(platform: str, toggle: ToggleKey) -> str | None:
    return _CHANNEL_ACTION_IDS.get(platform, {}).get(toggle)


def _comments_action_requested(tenant_id: str, platform: str) -> bool:
    actions = load_actions_section(tenant_id)
    action_id = action_id_for(platform, "comments")
    if not action_id:
        return False
    return action_enabled(actions, action_id)


def _binding_comment_webhook_subscribed(binding: Any) -> bool:
    fields = {str(item).strip().lower() for item in (getattr(binding, "webhook_subscribed_fields", ()) or ())}
    channel = str(getattr(binding, "channel", "") or "")
    auth_flow = str(getattr(binding, "auth_flow", "") or "")
    if channel == "facebook":
        return "feed" in fields
    if channel == "instagram" and auth_flow == "instagram_login":
        return COMMENTS_SUBSCRIPTION_FIELD in fields
    # Page-linked Instagram comments use App A instagram object subscription.
    # Binding fields may only mirror Page DM subscriptions; treat app ensure as recorded via "comments".
    return COMMENTS_SUBSCRIPTION_FIELD in fields


def _missing_comment_scopes(bindings: list[Any], *, registry: Any) -> list[str]:
    missing: set[str] = set()
    for binding in bindings:
        try:
            credential = registry.get_credential(binding)
            granted = set(credential.scopes)
        except Exception:
            missing |= set(required_comment_scopes_for_binding(binding))
            continue
        missing |= set(required_comment_scopes_for_binding(binding)) - granted
    return sorted(missing)


def comment_capability_state(tenant_id: str, platform: str) -> dict[str, Any]:
    """Truthful Comments capability matrix for one channel (never claims live_verified)."""

    platform_key = (platform or "").strip().lower()
    requested_enabled = (
        _comments_action_requested(tenant_id, platform_key) if platform_key in _CHANNEL_ACTION_IDS else False
    )
    bindings = _active_channel_bindings(tenant_id, platform_key) if platform_key in _CHANNEL_ACTION_IDS else []
    registry = get_meta_app_registry()
    missing_scopes = _missing_comment_scopes(bindings, registry=registry) if bindings else []
    permission_present = bool(bindings) and not missing_scopes
    webhook_subscribed = bool(bindings) and all(_binding_comment_webhook_subscribed(b) for b in bindings)
    live_verified = False
    if not bindings:
        blocker: str | None = "connect_channel_first"
    elif not permission_present:
        blocker = "missing_comment_permissions"
    elif not webhook_subscribed:
        blocker = "missing_comment_webhook"
    else:
        blocker = None

    effective_enabled = bool(requested_enabled and permission_present and webhook_subscribed)
    if live_verified and effective_enabled:
        status = "live_verified"
    elif effective_enabled:
        status = "ready"
    elif permission_present and webhook_subscribed:
        status = "ready_to_enable"
    elif permission_present and not webhook_subscribed:
        status = "needs_webhook"
    elif bindings:
        status = "needs_permission"
    else:
        status = "off"

    return {
        "requested_enabled": bool(requested_enabled),
        "permission_present": bool(permission_present),
        "webhook_subscribed": bool(webhook_subscribed),
        "live_verified": live_verified,
        "effective_enabled": effective_enabled,
        "missing_scopes": missing_scopes,
        "blocker": blocker,
        "status": status,
    }


def channel_toggle_states(tenant_id: str, platform: str) -> dict[str, bool]:
    """Return DM published state + Comments *effective* enabled (not raw requested)."""

    actions = load_actions_section(tenant_id)
    ids = _CHANNEL_ACTION_IDS.get(platform) or {}
    comments_state = comment_capability_state(tenant_id, platform)
    return {
        "dm": action_enabled(actions, ids["dm"]) if "dm" in ids else False,
        "comments": bool(comments_state["effective_enabled"]),
    }


def comments_enable_blocker(tenant_id: str, platform: str) -> str | None:
    """Explain why Enable comments cannot succeed yet (scopes / webhook / no binding)."""

    state = comment_capability_state(tenant_id, platform)
    blocker = state.get("blocker")
    return str(blocker) if blocker else None


async def clear_invalid_comments_enabled_state_async(
    *,
    tenant_id: str,
    platform: str,
    actor: str = "comments_state_reconcile",
) -> bool:
    """Async cleanup: turn off CM comments + per-asset when permissions are missing."""

    platform_key = (platform or "").strip().lower()
    if platform_key not in _CHANNEL_ACTION_IDS:
        return False
    state = comment_capability_state(tenant_id, platform_key)
    if not state["requested_enabled"]:
        return False
    if state["permission_present"]:
        return False
    action_id = action_id_for(platform_key, "comments")
    if not action_id:
        return False
    try:
        await _sync_comment_assets(tenant_id=tenant_id, platform=platform_key, enabled=False)
        _set_action_in_draft(tenant_id=tenant_id, action_id=action_id, enabled=False, actor=actor)
        await _publish_actions(tenant_id=tenant_id, actor=actor)
    except (ConflictError, ChannelToggleError, PublishBlockedError, PublishDisabledError):
        return False
    return True


def attach_channel_toggles(rows: list[dict[str, Any]], *, tenant_id: str) -> list[dict[str, Any]]:
    """Add ``toggles`` + ``comments_state`` to Instagram/Facebook rows."""

    out: list[dict[str, Any]] = []
    for row in rows:
        platform = str(row.get("platform") or "")
        if platform not in _CHANNEL_ACTION_IDS or row.get("coming_soon") is True:
            out.append(row)
            continue
        # Sync cleanup of false-enabled CM action when scopes are missing.
        # Publish is async; mark draft off when possible so subsequent reads stay truthful.
        state = comment_capability_state(tenant_id, platform)
        if state["requested_enabled"] and not state["permission_present"]:
            action_id = action_id_for(platform, "comments")
            if action_id:
                try:
                    _set_action_in_draft(
                        tenant_id=tenant_id,
                        action_id=action_id,
                        enabled=False,
                        actor="comments_state_reconcile",
                    )
                except ConflictError:
                    pass
            state = comment_capability_state(tenant_id, platform)
            # Force effective off even if draft publish has not landed yet.
            state = {
                **state,
                "requested_enabled": False,
                "effective_enabled": False,
                "status": "needs_permission"
                if state.get("blocker") == "missing_comment_permissions"
                else state["status"],
            }
        enriched = {
            **row,
            "toggles": {
                "dm": channel_toggle_states(tenant_id, platform)["dm"],
                "comments": bool(state["effective_enabled"]),
            },
            "comments_state": state,
        }
        blocker = state.get("blocker")
        if blocker:
            enriched["comments_blocker"] = blocker
        out.append(enriched)
    return out


def _active_channel_bindings(tenant_id: str, platform: str) -> list[Any]:
    registry = get_meta_app_registry()
    return [
        b
        for b in registry.list_bindings(include_inactive=False, include_superseded=False)
        if getattr(b, "tenant_id", None) == tenant_id
        and str(getattr(b, "channel", "") or "") == platform
        and str(getattr(b, "status", "") or "") == "active"
        and str(getattr(b, "app_key", "") or "") == APP_A_KEY
    ]


def _record_comment_webhook_fields(binding: Any, *, registry: Any, extra_fields: tuple[str, ...]) -> None:
    """Merge comment webhook fields onto the binding record without disconnecting assets."""

    try:
        with registry._locked():
            state = registry._read_unlocked()
            raw = state["bindings"].get(binding.binding_id)
            if not isinstance(raw, dict):
                return
            changed = dict(raw)
            existing = [str(item) for item in (changed.get("webhook_subscribed_fields") or [])]
            changed["webhook_subscribed_fields"] = sorted(
                {*existing, *[str(f) for f in extra_fields if str(f).strip()]}
            )
            changed["updated_at"] = time.time()
            state["bindings"][binding.binding_id] = changed
            registry._write_unlocked(state)
    except Exception:
        # Non-fatal: enable path already confirmed Meta subscription via Graph API.
        return


async def _sync_comment_assets(*, tenant_id: str, platform: str, enabled: bool) -> None:
    """Align per-asset comment_replies with the CM comments action for this channel."""

    registry = get_meta_app_registry()
    bindings = _active_channel_bindings(tenant_id, platform)
    if enabled and not bindings:
        raise ChannelToggleError(
            "Connect this channel before enabling comments.",
            status_code=409,
            code="COMMENT_CONNECT_REQUIRED",
        )
    if enabled:
        for binding in bindings:
            if not credential_has_comment_scopes(binding, registry):
                missing = _missing_comment_scopes([binding], registry=registry)
                detail = f" Missing: {', '.join(missing)}." if missing else ""
                raise ChannelToggleError(
                    _COMMENT_SCOPES_MISSING_MESSAGE + detail,
                    status_code=409,
                    code="COMMENT_SCOPES_MISSING",
                )

    for binding in bindings:
        previous = get_comment_reply_setting(
            tenant_id=tenant_id,
            app_key=binding.app_key,
            channel=binding.channel,
            asset_id=binding.asset_id,
        )
        set_comment_reply_setting(
            tenant_id=tenant_id,
            app_key=binding.app_key,
            channel=binding.channel,
            asset_id=binding.asset_id,
            enabled=enabled,
            instructions=previous.instructions,
        )
        if not enabled:
            continue
        try:
            if binding.channel == "facebook":
                await ensure_page_comment_webhook_subscription(binding, registry=registry)
                _record_comment_webhook_fields(binding, registry=registry, extra_fields=("feed",))
            else:
                await ensure_instagram_comment_app_webhook(app_key=binding.app_key)
                _record_comment_webhook_fields(
                    binding,
                    registry=registry,
                    extra_fields=(COMMENTS_SUBSCRIPTION_FIELD,),
                )
        except MetaOAuthError as exc:
            set_comment_reply_setting(
                tenant_id=tenant_id,
                app_key=binding.app_key,
                channel=binding.channel,
                asset_id=binding.asset_id,
                enabled=False,
                instructions=previous.instructions,
            )
            raise ChannelToggleError(str(exc), status_code=409, code="COMMENT_WEBHOOK_FAILED") from exc


async def sync_published_comment_assets_if_enabled(*, tenant_id: str, platform: str) -> None:
    """After Meta connect/reauth, sync per-asset comment switch when CM comments action is ON."""

    platform_key = (platform or "").strip().lower()
    if platform_key not in _CHANNEL_ACTION_IDS:
        return
    if not _comments_action_requested(tenant_id, platform_key):
        return
    state = comment_capability_state(tenant_id, platform_key)
    if not state["permission_present"]:
        # Reauth did not grant comment scopes — clear false requested enabled.
        await clear_invalid_comments_enabled_state_async(tenant_id=tenant_id, platform=platform_key)
        return
    await _sync_comment_assets(tenant_id=tenant_id, platform=platform_key, enabled=True)


def _set_action_in_draft(*, tenant_id: str, action_id: str, enabled: bool, actor: str) -> ActionsSection:
    envelope = get_draft("actions", tenant_id=tenant_id, create_default=True)
    section = ActionsSection.model_validate(envelope.payload or {})
    items = list(section.items)
    found = False
    next_items: list[ActionCapability] = []
    for item in items:
        if item.id == action_id:
            next_items.append(item.model_copy(update={"enabled": bool(enabled)}))
            found = True
        else:
            next_items.append(item)
    if not found:
        next_items.append(ActionCapability(id=action_id, enabled=bool(enabled)))
    next_section = ActionsSection(items=next_items, notes=section.notes)
    put_draft(
        "actions",
        payload=next_section.model_dump(),
        if_match=envelope.etag,
        tenant_id=tenant_id,
        updated_by=actor,
    )
    return next_section


async def _publish_actions(*, tenant_id: str, actor: str) -> None:
    try:
        ensure_publish_enabled()
    except PublishDisabledError as exc:
        raise ChannelToggleError(exc.message, status_code=403, code="PUBLISH_DISABLED") from exc

    try:
        if read_published_pointer(tenant_id) is None:
            await publish_draft_sections(
                tenant_id=tenant_id,
                published_by=actor,
                notes="mobile_integrations_channel_toggle",
                section_names=None,
            )
        else:
            await publish_draft_sections(
                tenant_id=tenant_id,
                published_by=actor,
                notes="mobile_integrations_channel_toggle:actions",
                section_names=["actions"],
            )
    except PublishBlockedError as exc:
        raise ChannelToggleError(
            exc.message,
            status_code=422,
            code="PUBLISH_BLOCKED",
        ) from exc


async def set_channel_toggle(
    *,
    tenant_id: str,
    platform: str,
    toggle: ToggleKey,
    enabled: bool,
    actor: str,
) -> dict[str, Any]:
    """Persist one channel capability toggle via CM Actions (+ comment assets when needed)."""

    platform_key = (platform or "").strip().lower()
    if platform_key not in _CHANNEL_ACTION_IDS:
        raise ChannelToggleError("Unsupported platform", status_code=404, code="UNKNOWN_PLATFORM")
    action_id = action_id_for(platform_key, toggle)
    if not action_id:
        raise ChannelToggleError("Unsupported toggle", status_code=400, code="UNKNOWN_TOGGLE")

    try:
        if toggle == "comments" and enabled:
            # Preflight + webhook sync BEFORE persisting enabled — never save a false ON.
            await _sync_comment_assets(tenant_id=tenant_id, platform=platform_key, enabled=True)
            _set_action_in_draft(
                tenant_id=tenant_id,
                action_id=action_id,
                enabled=True,
                actor=actor,
            )
            await _publish_actions(tenant_id=tenant_id, actor=actor)
        elif toggle == "comments" and not enabled:
            await _sync_comment_assets(tenant_id=tenant_id, platform=platform_key, enabled=False)
            _set_action_in_draft(
                tenant_id=tenant_id,
                action_id=action_id,
                enabled=False,
                actor=actor,
            )
            await _publish_actions(tenant_id=tenant_id, actor=actor)
        else:
            _set_action_in_draft(
                tenant_id=tenant_id,
                action_id=action_id,
                enabled=enabled,
                actor=actor,
            )
            await _publish_actions(tenant_id=tenant_id, actor=actor)
    except ConflictError as exc:
        raise ChannelToggleError(
            "Actions draft changed; reload and retry.",
            status_code=409,
            code="DRAFT_CONFLICT",
        ) from exc

    toggles = channel_toggle_states(tenant_id, platform_key)
    return {
        "toggles": toggles,
        "comments_state": comment_capability_state(tenant_id, platform_key),
    }
