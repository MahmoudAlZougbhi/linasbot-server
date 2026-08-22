"""Per-channel DM/comment enable flags for Linas AI Integrations.

App switches are owner intent for AI replies. Meta subscriptions are owned by
Connect/Disconnect, not by these toggles.

Mobile UI reads ``requested_enabled`` for toggle switches.
"""

from __future__ import annotations

import time
from typing import Any, Literal

from services.channel_capability_state import (
    action_id_for,
    canonical_channel_bindings,
    comment_capability_state,
    dm_capability_state,
    supported_platforms,
)
from services.cm.actions import load_actions_section
from services.cm.publish import PublishBlockedError, publish_draft_sections
from services.cm.publish_gate import PublishDisabledError, ensure_publish_enabled
from services.cm.schemas import ActionCapability, ActionsSection, SectionDraftEnvelope
from services.cm.storage import ConflictError, draft_section_path, get_draft, put_draft
from services.cm.version_store import read_published_pointer
from services.meta_app_registry import APP_A_KEY, get_meta_app_configs, get_meta_app_registry
from services.meta_comment_reply_settings import get_comment_reply_setting, set_comment_reply_setting
from services.meta_comment_webhooks import (
    ensure_instagram_comment_app_webhook,
    ensure_page_comment_webhook_subscription,
)
from services.meta_instagram_login_subscription import (
    COMMENTS_SUBSCRIPTION_FIELD,
    ensure_instagram_login_webhook_subscription,
)
from services.meta_oauth import MetaOAuthError

ChannelPlatform = Literal["instagram", "facebook"]
ToggleKey = Literal["dm", "comments"]

_COMMENT_SCOPES_MISSING_MESSAGE = (
    "Missing Meta comment permissions. Disconnect this channel, then Connect again to grant comment scopes."
)

__all__ = [
    "ChannelToggleError",
    "action_id_for",
    "attach_channel_toggles",
    "channel_toggle_states",
    "clear_invalid_comments_enabled_state_async",
    "comment_capability_state",
    "comments_enable_blocker",
    "enable_channel_defaults_after_connect",
    "ensure_comment_webhook_for_binding",
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


def channel_toggle_states(tenant_id: str, platform: str) -> dict[str, bool]:
    """Return DM and Comments requested switch state for Integrations."""

    comments_state = comment_capability_state(tenant_id, platform)
    dm_state = dm_capability_state(tenant_id, platform)
    return {
        # Mobile switches reflect CM *requested* state; effective gates live in *_state below.
        "dm": bool(dm_state["requested_enabled"]),
        "comments": bool(comments_state["requested_enabled"]),
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
    """Turn off CM comments only when the platform has no remaining active bindings.

    Unhealthy connections keep the owner's requested ON; status hints surface blockers.
    """

    platform_key = (platform or "").strip().lower()
    if platform_key not in supported_platforms():
        return False
    state = comment_capability_state(tenant_id, platform_key)
    if not state["requested_enabled"]:
        return False
    if canonical_channel_bindings(tenant_id, platform_key):
        return False
    try:
        await set_channel_toggle(
            tenant_id=tenant_id,
            platform=platform_key,
            toggle="comments",
            enabled=False,
            actor=actor,
        )
    except ChannelToggleError:
        return False
    return True


def attach_channel_toggles(rows: list[dict[str, Any]], *, tenant_id: str) -> list[dict[str, Any]]:
    """Add ``toggles`` + canonical ``comments_state`` / ``dm_state`` to Meta rows."""

    out: list[dict[str, Any]] = []
    for row in rows:
        platform = str(row.get("platform") or "")
        if platform == "tiktok" and row.get("coming_soon") is not True:
            from services.tiktok_business.toggles import attach_tiktok_row_toggles

            out.append(attach_tiktok_row_toggles(row))
            continue
        if platform not in supported_platforms() or row.get("coming_soon") is True:
            out.append(row)
            continue
        state = comment_capability_state(tenant_id, platform)
        dm_state = dm_capability_state(tenant_id, platform)
        enriched = {
            **row,
            "toggles": {
                "dm": bool(dm_state["requested_enabled"]),
                "comments": bool(state["requested_enabled"]),
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
                raise MetaOAuthError("Meta binding disappeared while recording webhook readiness")
            changed = dict(raw)
            existing = [str(item) for item in (changed.get("webhook_subscribed_fields") or [])]
            changed["webhook_subscribed_fields"] = sorted(
                {*existing, *[str(f) for f in extra_fields if str(f).strip()]}
            )
            changed["webhook_subscription_checked_at"] = time.time()
            changed["updated_at"] = time.time()
            state["bindings"][binding.binding_id] = changed
            registry._write_unlocked(state)
    except MetaOAuthError:
        raise
    except Exception as exc:
        raise MetaOAuthError("Meta webhook readiness could not be persisted") from exc


async def ensure_comment_webhook_for_binding(binding: Any, *, registry: Any) -> None:
    """Subscribe/verify comment webhooks for the canonical binding (idempotent)."""

    auth_flow = str(getattr(binding, "auth_flow", "") or "")
    if binding.channel == "facebook":
        await ensure_page_comment_webhook_subscription(binding, registry=registry)
        _record_comment_webhook_fields(
            binding, registry=registry, extra_fields=("feed", "messages", "messaging_postbacks", "standby")
        )
        return
    if auth_flow == "instagram_login":
        credential = registry.get_credential(binding)
        app = get_meta_app_configs()[binding.app_key]
        state = await ensure_instagram_login_webhook_subscription(
            binding,
            credential,
            registry=registry,
            graph_api_version=app.graph_api_version,
        )
        if not state.ready_for_comments:
            raise MetaOAuthError("Instagram comment webhook subscription is not confirmed")
        return
    await ensure_instagram_comment_app_webhook(app_key=binding.app_key)
    _record_comment_webhook_fields(
        binding,
        registry=registry,
        extra_fields=(COMMENTS_SUBSCRIPTION_FIELD, "messages", "messaging_postbacks"),
    )


async def _sync_comment_assets(*, tenant_id: str, platform: str, enabled: bool) -> None:
    """Align local per-asset comment AI switch with the CM comments action.

    Does not mutate Meta subscriptions. Webhooks stay on for the life of Connect.
    """

    bindings = canonical_channel_bindings(tenant_id, platform)
    if enabled and not bindings:
        raise ChannelToggleError(
            "Connect this channel before enabling comments.",
            status_code=409,
            code="COMMENT_CONNECT_REQUIRED",
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
        for binding in canonical_channel_bindings(tenant_id, platform_key):
            try:
                await ensure_comment_webhook_for_binding(binding, registry=registry)
            except MetaOAuthError as exc:
                raise ChannelToggleError(str(exc), status_code=409, code="COMMENT_WEBHOOK_FAILED") from exc
    return {
        "toggles": channel_toggle_states(tenant_id, platform_key),
        "comments_state": comment_capability_state(tenant_id, platform_key),
        "dm_state": dm_capability_state(tenant_id, platform_key),
    }


async def sync_published_comment_assets_if_enabled(*, tenant_id: str, platform: str) -> None:
    """After Meta connect/reauth, turn local comment AI on when the app Comments switch is ON."""

    platform_key = (platform or "").strip().lower()
    if platform_key not in supported_platforms():
        return
    state = comment_capability_state(tenant_id, platform_key)
    if not state["requested_enabled"]:
        return
    await _sync_comment_assets(tenant_id=tenant_id, platform=platform_key, enabled=True)


def _actions_draft_envelope(*, tenant_id: str, actor: str) -> SectionDraftEnvelope:
    """Load actions draft; seed from published CM when no draft file exists yet."""

    if draft_section_path(tenant_id, "actions").exists():
        return get_draft("actions", tenant_id=tenant_id, create_default=False)

    published = load_actions_section(tenant_id)
    if published is not None:
        return put_draft(
            "actions",
            payload=published.model_dump(),
            if_match="*",
            tenant_id=tenant_id,
            updated_by=actor,
            allow_create=True,
        )

    return get_draft("actions", tenant_id=tenant_id, create_default=True)


def _set_action_in_draft(*, tenant_id: str, action_id: str, enabled: bool, actor: str) -> ActionsSection:
    envelope = _actions_draft_envelope(tenant_id=tenant_id, actor=actor)
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


def _has_testing_binding(tenant_id: str, platform: str) -> bool:
    """True when this tenant/platform has a staged OAuth binding that is not active yet."""

    tenant = str(tenant_id or "").strip().lower()
    platform_key = (platform or "").strip().lower()
    for binding in get_meta_app_registry().list_bindings(include_inactive=True, include_superseded=False):
        if str(getattr(binding, "tenant_id", "") or "").strip().lower() != tenant:
            continue
        if str(getattr(binding, "channel", "") or "") != platform_key:
            continue
        if str(getattr(binding, "app_key", "") or "") != APP_A_KEY:
            continue
        if str(getattr(binding, "status", "") or "") == "testing":
            return True
    return False


async def enable_channel_defaults_after_connect(
    *,
    tenant_id: str,
    platform: str,
    actor: str,
    include_comments: bool = True,
) -> None:
    """After Meta connect, turn app DM + Comments ON. Meta webhooks stay as Connect left them."""

    platform_key = (platform or "").strip().lower()
    if platform_key not in supported_platforms():
        return
    toggles: tuple[ToggleKey, ...] = ("dm", "comments") if include_comments else ("dm",)
    for toggle in toggles:
        await set_channel_toggle(
            tenant_id=tenant_id,
            platform=platform_key,
            toggle=toggle,
            enabled=True,
            actor=actor,
            allow_testing_binding=toggle == "dm",
        )


async def set_channel_toggle(
    *,
    tenant_id: str,
    platform: str,
    toggle: ToggleKey,
    enabled: bool,
    actor: str,
    allow_testing_binding: bool = False,
) -> dict[str, Any]:
    """Persist one channel capability toggle via CM Actions (+ comment assets when needed)."""

    platform_key = (platform or "").strip().lower()
    if platform_key not in supported_platforms():
        raise ChannelToggleError("Unsupported platform", status_code=404, code="UNKNOWN_PLATFORM")
    action_id = action_id_for(platform_key, toggle)
    if not action_id:
        raise ChannelToggleError("Unsupported toggle", status_code=400, code="UNKNOWN_TOGGLE")

    if enabled and not canonical_channel_bindings(tenant_id, platform_key):
        if not (allow_testing_binding and _has_testing_binding(tenant_id, platform_key)):
            raise ChannelToggleError(
                "Connect this channel before enabling messaging.",
                status_code=409,
                code="CONNECT_REQUIRED",
            )

    if toggle == "comments" and enabled:
        from services.membership.comment_gate import CommentAutomationDenied, assert_comment_automation_allowed

        try:
            assert_comment_automation_allowed(tenant_id)
        except CommentAutomationDenied as exc:
            raise ChannelToggleError(str(exc), status_code=403, code=exc.code) from exc

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
