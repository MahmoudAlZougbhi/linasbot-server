"""Per-channel DM/comment enable flags for Linas AI Integrations.

Mirrors AI Setup → Actions switches and, for comments, syncs the
per-asset Meta comment-reply setting used at runtime.

Mobile UI reads ``effective_enabled`` from the canonical capability matrix only.
"""

from __future__ import annotations

import time
from typing import Any, Literal

from services.channel_capability_state import (
    action_id_for,
    active_channel_bindings,
    comment_capability_state,
    dm_capability_state,
    supported_platforms,
)
from services.cm.publish import PublishBlockedError, publish_draft_sections
from services.cm.publish_gate import PublishDisabledError, ensure_publish_enabled
from services.cm.schemas import ActionCapability, ActionsSection
from services.cm.storage import ConflictError, get_draft, put_draft
from services.cm.version_store import read_published_pointer
from services.meta_app_registry import get_meta_app_registry
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

_COMMENT_SCOPES_MISSING_MESSAGE = (
    "Missing Meta comment permissions. Use Manage Meta Access / Reconnect with Comment Access "
    "for the same Facebook Page / Instagram account (do not Disconnect Account)."
)

__all__ = [
    "ChannelToggleError",
    "action_id_for",
    "attach_channel_toggles",
    "channel_toggle_states",
    "clear_invalid_comments_enabled_state_async",
    "comment_capability_state",
    "comments_enable_blocker",
    "reconcile_comment_webhooks_for_platform",
    "set_channel_toggle",
    "supported_platforms",
    "sync_published_comment_assets_if_enabled",
]


class ChannelToggleError(Exception):
    def __init__(self, message: str, *, status_code: int = 400, code: str = "TOGGLE_ERROR") -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


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


def channel_toggle_states(tenant_id: str, platform: str) -> dict[str, bool]:
    """Return DM requested + Comments *effective* (never false Comments ON)."""

    comments_state = comment_capability_state(tenant_id, platform)
    dm_state = dm_capability_state(tenant_id, platform)
    return {
        # DMs: preserve existing CM toggle semantics (no false-OFF on empty field records).
        "dm": bool(dm_state["requested_enabled"]),
        "comments": bool(comments_state["effective_enabled"]),
    }


def comments_enable_blocker(tenant_id: str, platform: str) -> str | None:
    state = comment_capability_state(tenant_id, platform)
    blocker = state.get("blocker_code") or state.get("blocker")
    return str(blocker) if blocker else None


async def clear_invalid_comments_enabled_state_async(
    *,
    tenant_id: str,
    platform: str,
    actor: str = "comments_state_reconcile",
) -> bool:
    """Turn off CM comments + per-asset when permissions/health gates fail."""

    platform_key = (platform or "").strip().lower()
    if platform_key not in supported_platforms():
        return False
    state = comment_capability_state(tenant_id, platform_key)
    if not state["requested_enabled"]:
        return False
    if state["permission_present"] and state["connection_healthy"]:
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
    """Add ``toggles`` + canonical ``comments_state`` / ``dm_state`` to Meta rows."""

    out: list[dict[str, Any]] = []
    for row in rows:
        platform = str(row.get("platform") or "")
        if platform not in supported_platforms() or row.get("coming_soon") is True:
            out.append(row)
            continue
        state = comment_capability_state(tenant_id, platform)
        if state["requested_enabled"] and (not state["permission_present"] or not state["connection_healthy"]):
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
            state = {
                **state,
                "requested_enabled": False,
                "tenant_action_enabled": False,
                "effective_enabled": False,
                "status": "permission_required"
                if state.get("blocker_code") == "missing_comment_permissions"
                else state.get("status") or "disabled",
            }
        dm_state = dm_capability_state(tenant_id, platform)
        enriched = {
            **row,
            "toggles": {
                "dm": bool(dm_state["requested_enabled"]),
                "comments": bool(state["effective_enabled"]),
            },
            "comments_state": state,
            "dm_state": dm_state,
        }
        blocker = state.get("blocker_code") or state.get("blocker")
        if blocker:
            enriched["comments_blocker"] = blocker
        out.append(enriched)
    return out


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
            changed["webhook_subscription_checked_at"] = time.time()
            changed["updated_at"] = time.time()
            state["bindings"][binding.binding_id] = changed
            registry._write_unlocked(state)
    except Exception:
        return


async def _sync_comment_assets(*, tenant_id: str, platform: str, enabled: bool) -> None:
    """Align per-asset comment_replies with the CM comments action for this channel."""

    registry = get_meta_app_registry()
    bindings = active_channel_bindings(tenant_id, platform)
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
                _record_comment_webhook_fields(
                    binding, registry=registry, extra_fields=("feed", "messages", "messaging_postbacks")
                )
            else:
                await ensure_instagram_comment_app_webhook(app_key=binding.app_key)
                _record_comment_webhook_fields(
                    binding,
                    registry=registry,
                    extra_fields=(COMMENTS_SUBSCRIPTION_FIELD, "messages", "messaging_postbacks"),
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


async def reconcile_comment_webhooks_for_platform(*, tenant_id: str, platform: str) -> dict[str, Any]:
    """Best-effort comment webhook reconcile without disconnecting or revoking tokens."""

    platform_key = (platform or "").strip().lower()
    if platform_key not in supported_platforms():
        raise ChannelToggleError("Unsupported platform", status_code=404, code="UNKNOWN_PLATFORM")
    state = comment_capability_state(tenant_id, platform_key)
    if not state["permission_present"]:
        raise ChannelToggleError(
            state.get("blocker_message") or _COMMENT_SCOPES_MISSING_MESSAGE,
            status_code=409,
            code="COMMENT_SCOPES_MISSING",
        )
    if state["requested_enabled"]:
        await _sync_comment_assets(tenant_id=tenant_id, platform=platform_key, enabled=True)
    else:
        # Permissions present but Comments off — still ensure Meta fields when ops/UI asks.
        registry = get_meta_app_registry()
        for binding in active_channel_bindings(tenant_id, platform_key):
            try:
                if binding.channel == "facebook":
                    await ensure_page_comment_webhook_subscription(binding, registry=registry)
                    _record_comment_webhook_fields(
                        binding, registry=registry, extra_fields=("feed", "messages", "messaging_postbacks")
                    )
                else:
                    await ensure_instagram_comment_app_webhook(app_key=binding.app_key)
                    _record_comment_webhook_fields(
                        binding,
                        registry=registry,
                        extra_fields=(COMMENTS_SUBSCRIPTION_FIELD, "messages", "messaging_postbacks"),
                    )
            except MetaOAuthError as exc:
                raise ChannelToggleError(str(exc), status_code=409, code="COMMENT_WEBHOOK_FAILED") from exc
    return {
        "toggles": channel_toggle_states(tenant_id, platform_key),
        "comments_state": comment_capability_state(tenant_id, platform_key),
        "dm_state": dm_capability_state(tenant_id, platform_key),
    }


async def sync_published_comment_assets_if_enabled(*, tenant_id: str, platform: str) -> None:
    """After Meta connect/reauth, sync per-asset comment switch when CM comments action is ON."""

    platform_key = (platform or "").strip().lower()
    if platform_key not in supported_platforms():
        return
    state = comment_capability_state(tenant_id, platform_key)
    if not state["requested_enabled"]:
        return
    if not state["permission_present"] or not state["connection_healthy"]:
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
    if platform_key not in supported_platforms():
        raise ChannelToggleError("Unsupported platform", status_code=404, code="UNKNOWN_PLATFORM")
    action_id = action_id_for(platform_key, toggle)
    if not action_id:
        raise ChannelToggleError("Unsupported toggle", status_code=400, code="UNKNOWN_TOGGLE")

    try:
        if toggle == "comments" and enabled:
            await _sync_comment_assets(tenant_id=tenant_id, platform=platform_key, enabled=True)
            _set_action_in_draft(tenant_id=tenant_id, action_id=action_id, enabled=True, actor=actor)
            await _publish_actions(tenant_id=tenant_id, actor=actor)
        elif toggle == "comments" and not enabled:
            await _sync_comment_assets(tenant_id=tenant_id, platform=platform_key, enabled=False)
            _set_action_in_draft(tenant_id=tenant_id, action_id=action_id, enabled=False, actor=actor)
            await _publish_actions(tenant_id=tenant_id, actor=actor)
        else:
            _set_action_in_draft(tenant_id=tenant_id, action_id=action_id, enabled=enabled, actor=actor)
            await _publish_actions(tenant_id=tenant_id, actor=actor)
    except ConflictError as exc:
        raise ChannelToggleError(
            "Actions draft changed; reload and retry.",
            status_code=409,
            code="DRAFT_CONFLICT",
        ) from exc

    return {
        "toggles": channel_toggle_states(tenant_id, platform_key),
        "comments_state": comment_capability_state(tenant_id, platform_key),
        "dm_state": dm_capability_state(tenant_id, platform_key),
    }
