"""Meta connection lifecycle routes: disconnect/reconnect/activate/rollback/comment-replies (LOC split)."""

from __future__ import annotations

import asyncio
import time
from typing import Any, cast

from fastapi import Body, HTTPException, Request

from modules.api_security import require_permission
from modules.core import app
from modules.meta_connections_api_helpers import (
    _active_conflict,
    _tenant_binding,
)
from services.channel_capability_toggles import ensure_comment_webhook_for_binding
from services.meta_app_registry import (
    APP_A_KEY,
    APP_B_KEY,
    MetaAssetBinding,
    MetaRegistryError,
    get_meta_app_registry,
)
from services.meta_comment_reply_settings import get_comment_reply_setting, set_comment_reply_setting
from services.meta_comment_webhooks import credential_has_comment_scopes
from services.meta_connection_disconnect import disconnect_meta_binding_set
from services.meta_graph_routing import required_comment_scopes_for_binding
from services.meta_instagram_login_subscription_recovery import retry_instagram_login_webhook_subscription
from services.meta_oauth import (
    MetaOAuthError,
    subscribe_binding_webhook,
)
from services.meta_oauth_graph import (
    _other_active_binding_shares_page,
    _unsubscribe_binding_webhook_locked_raw,
    desired_binding_webhook_subscription,
)
from services.meta_oauth_page_lock import lock_facebook_page_oauth_operation
from services.meta_page_subscription_transaction import (
    PageSubscriptionMutation,
    capture_page_subscription_snapshots,
    compensate_page_subscription_failure,
    page_subscription_identity,
    reconcile_page_activation_after_exception,
    reconcile_page_rollback_after_exception,
)
from services.mobile_integrations_display import bindings_for_disconnect


async def _activate_meta_connection_locked(
    binding: MetaAssetBinding,
    previous: MetaAssetBinding | None,
    *,
    actor_id: str,
    registry: Any,
) -> MetaAssetBinding:
    """Mutate every provider row first, then atomically flip local routing."""

    current_conflict = _active_conflict(binding)
    if (current_conflict.binding_id if current_conflict else "") != (previous.binding_id if previous else "") or (
        current_conflict is not None
        and previous is not None
        and page_subscription_identity(current_conflict) != page_subscription_identity(previous)
    ):
        raise MetaRegistryError("Active Meta binding changed before Page cutover")
    previous = current_conflict
    registry.assert_binding_can_activate(
        binding.binding_id,
        expected_generation=binding.generation,
        replacing_binding_id=previous.binding_id if previous else "",
    )
    staged = MetaAssetBinding(**{**binding.__dict__, "status": "active"})
    delete_previous = (
        previous is not None
        and page_subscription_identity(previous) != page_subscription_identity(staged)
        and not _other_active_binding_shares_page(previous, registry)
    )
    candidates = (staged,) + ((previous,) if delete_previous and previous is not None else ())
    snapshots = await capture_page_subscription_snapshots(candidates, registry=registry)
    mutations: list[PageSubscriptionMutation] = []
    desired = desired_binding_webhook_subscription(staged, registry=registry)
    try:
        mutations.append(
            PageSubscriptionMutation(
                staged,
                snapshots[page_subscription_identity(staged)],
                desired,
            )
        )
        await subscribe_binding_webhook(staged, registry=registry)
        if delete_previous and previous is not None:
            mutations.append(
                PageSubscriptionMutation(
                    previous,
                    snapshots[page_subscription_identity(previous)],
                    None,
                )
            )
            await _unsubscribe_binding_webhook_locked_raw(previous, registry=registry, client=None)
        return cast(
            MetaAssetBinding,
            registry.activate_staged_binding(
                binding.binding_id,
                actor_id=actor_id,
                expected_generation=binding.generation,
                replace_existing=previous is not None,
            ),
        )
    except BaseException as exc:  # noqa: BLE001 - cancellation must compensate too
        try:
            committed = reconcile_page_activation_after_exception(
                (binding,),
                expected_fields={binding.binding_id: desired},
                registry=registry,
            )
        except MetaOAuthError as reconciliation_error:
            if isinstance(exc, asyncio.CancelledError):
                raise exc from reconciliation_error
            raise reconciliation_error from exc
        if committed is not None:
            if isinstance(exc, asyncio.CancelledError):
                raise
            return committed[0]
        await compensate_page_subscription_failure(exc, mutations, registry=registry)
        raise


async def _rollback_meta_connection_locked(
    binding: MetaAssetBinding,
    previous: MetaAssetBinding,
    *,
    actor_id: str,
    registry: Any,
) -> MetaAssetBinding:
    """Restore exact provider state on any failed or cancelled rollback."""

    latest = {item.binding_id: item for item in registry.list_bindings()}
    current_binding = latest.get(binding.binding_id)
    current_previous = latest.get(previous.binding_id)
    if (
        current_binding is None
        or current_previous is None
        or current_binding.generation != binding.generation
        or current_previous.generation != previous.generation
        or page_subscription_identity(current_binding) != page_subscription_identity(binding)
        or page_subscription_identity(current_previous) != page_subscription_identity(previous)
    ):
        raise MetaRegistryError("Meta rollback bindings changed before Page cutover")
    binding = current_binding
    previous = current_previous
    staged_previous = MetaAssetBinding(**{**previous.__dict__, "status": "active"})
    registry.assert_binding_can_activate(
        previous.binding_id,
        expected_generation=previous.generation,
        replacing_binding_id=binding.binding_id,
    )
    delete_current = (
        binding.active
        and page_subscription_identity(binding) != page_subscription_identity(staged_previous)
        and not _other_active_binding_shares_page(binding, registry)
    )
    candidates = (staged_previous,) + ((binding,) if delete_current else ())
    snapshots = await capture_page_subscription_snapshots(candidates, registry=registry)
    mutations: list[PageSubscriptionMutation] = []
    desired = desired_binding_webhook_subscription(staged_previous, registry=registry)
    try:
        mutations.append(
            PageSubscriptionMutation(
                staged_previous,
                snapshots[page_subscription_identity(staged_previous)],
                desired,
            )
        )
        await subscribe_binding_webhook(staged_previous, registry=registry)
        if delete_current:
            mutations.append(
                PageSubscriptionMutation(
                    binding,
                    snapshots[page_subscription_identity(binding)],
                    None,
                )
            )
            await _unsubscribe_binding_webhook_locked_raw(binding, registry=registry, client=None)
        return cast(MetaAssetBinding, registry.rollback_binding(binding.binding_id, actor_id=actor_id))
    except BaseException as exc:  # noqa: BLE001 - cancellation must compensate too
        try:
            committed = reconcile_page_rollback_after_exception(
                binding,
                previous,
                expected_previous_fields=desired,
                registry=registry,
            )
        except MetaOAuthError as reconciliation_error:
            if isinstance(exc, asyncio.CancelledError):
                raise exc from reconciliation_error
            raise reconciliation_error from exc
        if committed is not None:
            if isinstance(exc, asyncio.CancelledError):
                raise
            return committed
        await compensate_page_subscription_failure(exc, mutations, registry=registry)
        raise


@app.post("/api/meta/connections/{binding_id}/disconnect")
async def disconnect_meta_connection(binding_id: str, request: Request) -> Any:
    session = require_permission(request, "settings")
    binding = _tenant_binding(binding_id, session.tenant_id)
    platform = str(binding.channel or "").strip().lower()
    registry = get_meta_app_registry()
    try:
        targets = bindings_for_disconnect(
            session.tenant_id,
            platform,
            asset_id=binding.asset_id,
            registry=registry,
        )
        if not targets:
            targets = [binding]
        disconnected = await disconnect_meta_binding_set(
            targets,
            actor_id=session.user_id or session.email,
            registry=registry,
            asset_id=binding.asset_id,
        )
        updated = next(
            (item for item in disconnected if item.binding_id == binding.binding_id),
            disconnected[0],
        )
    except (MetaOAuthError, MetaRegistryError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    # Force DM + Comments OFF once no active binding remains for this platform.
    if platform in {"instagram", "facebook"}:
        from services.channel_capability_disconnect import clear_channel_toggles_after_disconnect

        await clear_channel_toggles_after_disconnect(
            tenant_id=session.tenant_id,
            platform=platform,
            actor=session.user_id or session.email or "meta_disconnect",
        )
    return {
        "success": True,
        "connection": updated.public_dict(),
        "connections": [item.public_dict() for item in disconnected],
    }


@app.post("/api/meta/connections/{binding_id}/instagram-login/retry-webhook")
async def retry_instagram_login_webhook_setup(binding_id: str, request: Request) -> Any:
    session = require_permission(request, "settings")
    binding = _tenant_binding(binding_id, session.tenant_id)
    if binding.auth_flow != "instagram_login":
        raise HTTPException(status_code=409, detail="Webhook retry applies only to Instagram Login connections")
    try:
        state = await retry_instagram_login_webhook_subscription(
            binding.binding_id,
            actor_id=session.user_id or session.email,
        )
    except MetaOAuthError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    refreshed = _tenant_binding(binding_id, session.tenant_id)
    public = refreshed.public_dict()
    public["webhook_subscription"] = state.public_dict()
    return {
        "success": state.ready_for_dm,
        "connection": public,
        "webhook_subscription": state.public_dict(),
    }


@app.post("/api/meta/connections/{binding_id}/reconnect")
async def reconnect_meta_connection(binding_id: str, request: Request) -> Any:
    """Reconnect requires a fresh OAuth authorization — token reuse is not supported."""

    session = require_permission(request, "settings")
    binding = _tenant_binding(binding_id, session.tenant_id)
    if binding.status not in {"disconnected", "inactive"}:
        raise HTTPException(status_code=409, detail="Connection is already active or cannot be reconnected here")
    channel = str(binding.channel or "").strip().lower()
    if binding.auth_flow == "instagram_login" or channel == "instagram":
        raise HTTPException(
            status_code=409,
            detail="Disconnect Instagram, then use Connect Instagram to authorize again.",
        )
    raise HTTPException(
        status_code=409,
        detail="Disconnect this channel, then use Connect to run a fresh Meta authorization.",
    )


@app.post("/api/meta/connections/{binding_id}/activate")
async def activate_meta_connection(binding_id: str, request: Request) -> Any:
    session = require_permission(request, "settings")
    binding = _tenant_binding(binding_id, session.tenant_id)
    if binding.app_key not in {APP_A_KEY, APP_B_KEY} or binding.status not in {"testing", "inactive"}:
        raise HTTPException(status_code=409, detail="Connection is not eligible for activation")
    if session.tenant_id != "linas":
        from services.cm.version_store import load_published_content

        try:
            load_published_content(session.tenant_id)
        except Exception as exc:
            raise HTTPException(status_code=409, detail="Tenant AI content is not published") from exc
    registry = get_meta_app_registry()
    previous = _active_conflict(binding)
    try:
        async with lock_facebook_page_oauth_operation(
            registry,
            app_key=binding.app_key,
            page_ids=tuple(
                sorted(
                    {
                        binding.page_id,
                        previous.page_id if previous is not None else "",
                    }
                    - {""}
                )
            ),
        ):
            updated = await _activate_meta_connection_locked(
                binding,
                previous,
                actor_id=session.user_id or session.email,
                registry=registry,
            )
    except (MetaOAuthError, MetaRegistryError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"success": True, "connection": updated.public_dict()}


@app.post("/api/meta/connections/{binding_id}/rollback")
async def rollback_meta_connection(binding_id: str, request: Request) -> Any:
    session = require_permission(request, "settings")
    binding = _tenant_binding(binding_id, session.tenant_id)
    registry = get_meta_app_registry()
    previous = next(
        (item for item in registry.list_bindings() if item.binding_id == binding.previous_binding_id),
        None,
    )
    if previous is None or previous.tenant_id != session.tenant_id:
        raise HTTPException(status_code=409, detail="Previous Meta connection is unavailable")
    try:
        async with lock_facebook_page_oauth_operation(
            registry,
            app_key=binding.app_key,
            page_ids=tuple({binding.page_id, previous.page_id}),
        ):
            restored = await _rollback_meta_connection_locked(
                binding,
                previous,
                actor_id=session.user_id or session.email,
                registry=registry,
            )
    except (MetaOAuthError, MetaRegistryError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"success": True, "connection": restored.public_dict()}


@app.patch("/api/meta/connections/{binding_id}/comment-replies")
async def update_meta_comment_replies(
    binding_id: str,
    request: Request,
    body: dict[str, Any] = Body(default={}),
) -> Any:
    session = require_permission(request, "settings")
    binding = _tenant_binding(binding_id, session.tenant_id)
    if binding.app_key != APP_A_KEY:
        raise HTTPException(status_code=409, detail="Comment replies are only available for App A connections")
    if binding.status != "active":
        raise HTTPException(status_code=409, detail="Only active connections can change comment reply settings")

    enabled = bool(body.get("enabled"))
    instructions = str(body.get("instructions") or "").strip()
    if enabled:
        from services.membership.comment_gate import CommentAutomationDenied, assert_comment_automation_allowed

        try:
            assert_comment_automation_allowed(binding.tenant_id)
        except CommentAutomationDenied as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
    if enabled and not credential_has_comment_scopes(binding):
        raise HTTPException(
            status_code=409,
            detail=(
                "Missing Meta comment permissions. Disconnect this channel, then Connect again to grant comment scopes."
            ),
        )
    if enabled:
        from services.cm.actions import comments_action_enabled
        from services.cm.constants import tenant_uses_cm_runtime

        if tenant_uses_cm_runtime(binding.tenant_id) and not comments_action_enabled(
            binding.tenant_id, binding.channel
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    "Enable the matching Comments action in AI Setup → Actions "
                    "and publish before turning on per-asset comment replies."
                ),
            )

    previous = get_comment_reply_setting(
        tenant_id=binding.tenant_id,
        app_key=binding.app_key,
        channel=binding.channel,
        asset_id=binding.asset_id,
    )
    updated_setting = set_comment_reply_setting(
        tenant_id=binding.tenant_id,
        app_key=binding.app_key,
        channel=binding.channel,
        asset_id=binding.asset_id,
        enabled=enabled,
        instructions=instructions,
    )
    registry = get_meta_app_registry()
    registry._append_audit(
        {
            "event": "comment_replies_setting_changed",
            "tenant_id": binding.tenant_id,
            "binding_id": binding.binding_id,
            "channel": binding.channel,
            "asset_id_masked": binding.asset_id[-6:],
            "enabled": enabled,
            "previous_enabled": previous.enabled,
            "actor_id": session.user_id or session.email,
            "timestamp": time.time(),
        }
    )

    if enabled:
        try:
            await ensure_comment_webhook_for_binding(binding, registry=registry)
        except MetaOAuthError as exc:
            set_comment_reply_setting(
                tenant_id=binding.tenant_id,
                app_key=binding.app_key,
                channel=binding.channel,
                asset_id=binding.asset_id,
                enabled=False,
                instructions=instructions,
            )
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    public = binding.public_dict()
    from services.cm.actions import comments_enforcement_decision

    comment_decision = comments_enforcement_decision(
        tenant_id=binding.tenant_id,
        channel=binding.channel,
        per_asset_enabled=bool(updated_setting.enabled),
        granted_scopes=None,
    )
    public["comment_replies"] = {
        **updated_setting.public_dict(),
        "scopes_required": sorted(required_comment_scopes_for_binding(binding)),
        "scopes_ready": credential_has_comment_scopes(binding, registry),
        "cm_action_enabled": bool(comment_decision["readiness"].get("cm_action_enabled")),
        "cm_enforcement_allow": bool(comment_decision["allow"]),
        "cm_enforcement_reason": comment_decision["reason"],
        "readiness": comment_decision["readiness"],
        "live_verified": False,
    }
    return {"success": True, "comment_replies": public["comment_replies"]}
