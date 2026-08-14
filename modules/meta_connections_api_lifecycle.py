"""Meta connection lifecycle routes: disconnect/reconnect/activate/rollback/comment-replies (LOC split)."""

from __future__ import annotations

import time
from typing import Any

from fastapi import Body, HTTPException, Request

from modules.api_security import require_permission
from modules.core import app
from modules.meta_connections_api_helpers import (
    _active_conflict,
    _subscription_identity,
    _tenant_binding,
)
from services.meta_app_registry import (
    APP_A_KEY,
    APP_B_KEY,
    MetaAssetBinding,
    MetaRegistryError,
    get_meta_app_registry,
)
from services.meta_comment_reply_settings import get_comment_reply_setting, set_comment_reply_setting
from services.meta_comment_webhooks import (
    credential_has_comment_scopes,
    ensure_instagram_comment_app_webhook,
    ensure_page_comment_webhook_subscription,
    required_comment_scopes,
)
from services.meta_instagram_login_subscription_recovery import retry_instagram_login_webhook_subscription
from services.meta_oauth import (
    MetaOAuthError,
    disconnect_binding_webhook,
    subscribe_binding_webhook,
    unsubscribe_binding_webhook,
)


@app.post("/api/meta/connections/{binding_id}/disconnect")
async def disconnect_meta_connection(binding_id: str, request: Request) -> Any:
    session = require_permission(request, "settings")
    binding = _tenant_binding(binding_id, session.tenant_id)
    platform = str(binding.channel or "").strip().lower()
    registry = get_meta_app_registry()
    try:
        if binding.active:
            updated = await disconnect_binding_webhook(
                binding,
                actor_id=session.user_id or session.email,
            )
        else:
            updated = registry.set_binding_status(
                binding.binding_id,
                status="disconnected",
                actor_id=session.user_id or session.email,
                expected_generation=binding.generation,
            )
            updated = registry.archive_binding_credential(
                binding.binding_id,
                actor_id=session.user_id or session.email,
                expected_generation=updated.generation,
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
    return {"success": True, "connection": updated.public_dict()}


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
    try:
        previous = _active_conflict(binding)
        registry.assert_binding_can_activate(
            binding.binding_id,
            expected_generation=binding.generation,
            replacing_binding_id=previous.binding_id if previous else "",
        )
        # Subscribe while the binding is still ignored by webhook routing, then
        # atomically flip the exclusive active index. On conflict, undo subscription.
        staged = MetaAssetBinding(**{**binding.__dict__, "status": "active"})
        await subscribe_binding_webhook(staged, registry=registry)
        try:
            updated = registry.activate_staged_binding(
                binding.binding_id,
                actor_id=session.user_id or session.email,
                expected_generation=binding.generation,
                replace_existing=previous is not None,
            )
        except MetaRegistryError:
            await unsubscribe_binding_webhook(staged, registry=registry)
            raise
        # The registry flip above is the response boundary: only the new binding
        # can answer. Remove the old external subscription after the atomic flip.
        # A same-app/same-Page reconnect shares one Meta subscription and must not
        # unsubscribe it merely because its encrypted token was rotated.
        if previous and _subscription_identity(previous) != _subscription_identity(updated):
            try:
                await unsubscribe_binding_webhook(previous, registry=registry)
            except MetaOAuthError as cleanup_error:
                # Restore the former provider first. Even if Meta's unsubscribe
                # outcome was ambiguous, the inactive new binding cannot answer.
                restore_errors: list[str] = []
                try:
                    await subscribe_binding_webhook(
                        MetaAssetBinding(**{**previous.__dict__, "status": "active"}),
                        registry=registry,
                    )
                except MetaOAuthError as exc:
                    restore_errors.append(type(exc).__name__)
                try:
                    registry.rollback_binding(updated.binding_id, actor_id=session.user_id or session.email)
                except MetaRegistryError as exc:
                    restore_errors.append(type(exc).__name__)
                try:
                    await unsubscribe_binding_webhook(staged, registry=registry)
                except MetaOAuthError as exc:
                    restore_errors.append(type(exc).__name__)
                if restore_errors:
                    raise MetaOAuthError(
                        "Provider cutover failed and requires subscription diagnostics"
                    ) from cleanup_error
                raise MetaOAuthError("Provider cutover failed; the previous binding was restored") from cleanup_error
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
    staged_previous = MetaAssetBinding(**{**previous.__dict__, "status": "active"})
    try:
        registry.assert_binding_can_activate(
            previous.binding_id,
            expected_generation=previous.generation,
            replacing_binding_id=binding.binding_id,
        )
        await subscribe_binding_webhook(staged_previous, registry=registry)
        if binding.active:
            await unsubscribe_binding_webhook(binding, registry=registry)
        try:
            restored = registry.rollback_binding(binding.binding_id, actor_id=session.user_id or session.email)
        except MetaRegistryError:
            await unsubscribe_binding_webhook(staged_previous, registry=registry)
            if binding.active:
                await subscribe_binding_webhook(binding, registry=registry)
            raise
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
            if binding.channel == "facebook":
                await ensure_page_comment_webhook_subscription(binding, registry=registry)
            else:
                await ensure_instagram_comment_app_webhook(app_key=binding.app_key)
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
        "scopes_required": sorted(required_comment_scopes(binding.channel)),
        "scopes_ready": credential_has_comment_scopes(binding, registry),
        "cm_action_enabled": bool(comment_decision["readiness"].get("cm_action_enabled")),
        "cm_enforcement_allow": bool(comment_decision["allow"]),
        "cm_enforcement_reason": comment_decision["reason"],
        "readiness": comment_decision["readiness"],
        "live_verified": False,
    }
    return {"success": True, "comment_replies": public["comment_replies"]}
