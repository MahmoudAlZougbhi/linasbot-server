"""Per-channel DM/comment enable flags for Linas AI Integrations.

Mirrors the web Content Management → Actions switches
(``respond_{facebook|instagram}_{dm|comments}``) and, for comments, also syncs
the per-asset Meta comment-reply setting used at runtime.
"""

from __future__ import annotations

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
from services.meta_graph_routing import credential_has_comment_scopes
from services.meta_oauth import MetaOAuthError

ChannelPlatform = Literal["instagram", "facebook"]
ToggleKey = Literal["dm", "comments"]

_CHANNEL_ACTION_IDS: dict[str, dict[str, str]] = {
    "instagram": {"dm": ACTION_INSTAGRAM_DM, "comments": ACTION_INSTAGRAM_COMMENTS},
    "facebook": {"dm": ACTION_FACEBOOK_DM, "comments": ACTION_FACEBOOK_COMMENTS},
}


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


def channel_toggle_states(tenant_id: str, platform: str) -> dict[str, bool]:
    """Return published CM action state for DM + comments on one channel."""
    actions = load_actions_section(tenant_id)
    ids = _CHANNEL_ACTION_IDS.get(platform) or {}
    return {
        "dm": action_enabled(actions, ids["dm"]) if "dm" in ids else False,
        "comments": action_enabled(actions, ids["comments"]) if "comments" in ids else False,
    }


def attach_channel_toggles(rows: list[dict[str, Any]], *, tenant_id: str) -> list[dict[str, Any]]:
    """Add ``toggles`` to Instagram/Facebook rows; leave coming-soon rows untouched."""
    out: list[dict[str, Any]] = []
    for row in rows:
        platform = str(row.get("platform") or "")
        if platform not in _CHANNEL_ACTION_IDS or row.get("coming_soon") is True:
            out.append(row)
            continue
        out.append({**row, "toggles": channel_toggle_states(tenant_id, platform)})
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


async def _sync_comment_assets(*, tenant_id: str, platform: str, enabled: bool) -> None:
    """Align per-asset comment_replies with the CM comments action for this channel."""
    registry = get_meta_app_registry()
    bindings = _active_channel_bindings(tenant_id, platform)
    if enabled and not bindings:
        # CM action can still be on; per-asset applies once a page/account is connected.
        return
    if enabled:
        for binding in bindings:
            if not credential_has_comment_scopes(binding, registry):
                raise ChannelToggleError(
                    "Missing Meta comment permissions. Reconnect Instagram/Facebook with comment access.",
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
            else:
                await ensure_instagram_comment_app_webhook(app_key=binding.app_key)
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
) -> dict[str, bool]:
    """Persist one channel capability toggle via CM Actions (+ comment assets when needed)."""
    platform_key = (platform or "").strip().lower()
    if platform_key not in _CHANNEL_ACTION_IDS:
        raise ChannelToggleError("Unsupported platform", status_code=404, code="UNKNOWN_PLATFORM")
    action_id = action_id_for(platform_key, toggle)
    if not action_id:
        raise ChannelToggleError("Unsupported toggle", status_code=400, code="UNKNOWN_TOGGLE")

    try:
        if toggle == "comments" and not enabled:
            await _sync_comment_assets(tenant_id=tenant_id, platform=platform_key, enabled=False)

        _set_action_in_draft(
            tenant_id=tenant_id,
            action_id=action_id,
            enabled=enabled,
            actor=actor,
        )
        await _publish_actions(tenant_id=tenant_id, actor=actor)

        if toggle == "comments" and enabled:
            await _sync_comment_assets(tenant_id=tenant_id, platform=platform_key, enabled=True)
    except ConflictError as exc:
        raise ChannelToggleError(
            "Actions draft changed; reload and retry.",
            status_code=409,
            code="DRAFT_CONFLICT",
        ) from exc

    return channel_toggle_states(tenant_id, platform_key)
