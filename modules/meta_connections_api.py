"""Authenticated, tenant-isolated control plane for Meta App B connections."""

from __future__ import annotations

import time
from typing import Any

from fastapi import Body, HTTPException, Query, Request
from fastapi.responses import RedirectResponse

from modules.api_security import require_permission
from modules.core import app
from services.meta_app_registry import (
    APP_A_KEY,
    APP_B_KEY,
    MetaAssetBinding,
    MetaRegistryError,
    _bindings_share_exclusive_asset,
    get_meta_app_configs,
    get_meta_app_registry,
    meta_multi_app_registry_enabled,
)
from services.meta_comment_reply_settings import get_comment_reply_setting, set_comment_reply_setting
from services.meta_comment_webhooks import (
    credential_has_comment_scopes,
    ensure_instagram_comment_app_webhook,
    ensure_page_comment_webhook_subscription,
    required_comment_scopes,
)
from services.meta_graph_routing import required_comment_scopes_for_binding
from services.meta_instagram_login_config import instagram_login_config_status
from services.meta_instagram_login_oauth import begin_instagram_login, complete_instagram_login
from services.meta_instagram_login_subscription_recovery import retry_instagram_login_webhook_subscription
from services.meta_oauth import (
    MetaOAuthError,
    begin_meta_business_login,
    complete_meta_business_login,
    disconnect_binding_webhook,
    normalize_oauth_flow_channel,
    subscribe_binding_webhook,
    unsubscribe_binding_webhook,
)
from services.meta_oauth_return import (
    consume_return_surface_from_state,
    normalize_return_surface,
    oauth_completion_redirect_url,
)


def _query_text(value: Any) -> str:
    """Normalize FastAPI Query defaults when handlers are awaited directly in tests."""

    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    # Query()/Path() objects are truthy but should behave as empty defaults.
    if hasattr(value, "default") and not isinstance(value, (bytes, bytearray)):
        return ""
    return str(value).strip()


def _tenant_binding(binding_id: str, tenant_id: str) -> MetaAssetBinding:
    registry = get_meta_app_registry()
    binding = next(
        (item for item in registry.list_bindings() if item.binding_id == binding_id and item.tenant_id == tenant_id),
        None,
    )
    if binding is None:
        raise HTTPException(status_code=404, detail="Meta connection not found")
    return binding


def _subscription_identity(binding: MetaAssetBinding) -> tuple[str, str]:
    """Meta Page subscriptions are unique per app and Page, not per token."""

    return binding.app_key, binding.page_id


def _active_conflict(binding: MetaAssetBinding) -> MetaAssetBinding | None:
    matches = [
        item
        for item in get_meta_app_registry().list_bindings(include_inactive=False, include_superseded=False)
        if item.binding_id != binding.binding_id
        and item.tenant_id == binding.tenant_id
        and _bindings_share_exclusive_asset(item, binding)
    ]
    if len(matches) > 1:
        raise MetaRegistryError("Active Meta binding indexes are inconsistent")
    return matches[0] if matches else None


def _authorization_title(app_key: str | None) -> str:
    if app_key == APP_A_KEY:
        return "Meta authorization — App A"
    return "Connected through Linas AI"


@app.get("/api/meta/connections")
async def list_meta_connections(request: Request) -> Any:
    session = require_permission(request, "settings")
    if not meta_multi_app_registry_enabled():
        return {
            "success": True,
            "registry_enabled": False,
            "apps": [config.public_dict() for config in get_meta_app_configs().values()],
            "connections": [],
        }
    registry = get_meta_app_registry()
    registry.archive_superseded_duplicate_bindings(actor_id=session.user_id or session.email)
    connections: list[dict[str, Any]] = []
    for binding in registry.list_bindings(include_superseded=False):
        if binding.tenant_id != session.tenant_id:
            continue
        public = binding.public_dict()
        try:
            credential = registry.get_credential(binding)
            public["token_status"] = (
                "expired" if credential.expires_at and credential.expires_at <= int(time.time()) else "valid"
            )
            public["expires_at"] = credential.expires_at
            public["granted_permissions"] = sorted(credential.scopes)
            public["declined_permissions"] = sorted(credential.declined_scopes)
            if not public.get("authorized_meta_user_id_hash"):
                from services.meta_app_registry import authorized_meta_user_id_hash

                public["authorized_meta_user_id_hash"] = authorized_meta_user_id_hash(
                    credential.authorized_meta_user_id
                )
        except MetaRegistryError:
            public["token_status"] = "unavailable"
            public["expires_at"] = None
            public["granted_permissions"] = []
            public["declined_permissions"] = []
        comment_setting = get_comment_reply_setting(
            tenant_id=binding.tenant_id,
            app_key=binding.app_key,
            channel=binding.channel,
            asset_id=binding.asset_id,
        )
        from services.cm.actions import comments_enforcement_decision

        comment_decision = comments_enforcement_decision(
            tenant_id=binding.tenant_id,
            channel=binding.channel,
            per_asset_enabled=bool(comment_setting.enabled),
            granted_scopes=set(public.get("granted_permissions") or []),
        )
        public["comment_replies"] = {
            **comment_setting.public_dict(),
            "scopes_granted": sorted(
                required_comment_scopes_for_binding(binding) & set(public.get("granted_permissions") or [])
            ),
            "scopes_required": sorted(required_comment_scopes_for_binding(binding)),
            "scopes_ready": credential_has_comment_scopes(binding, registry),
            "cm_action_enabled": bool(comment_decision["readiness"].get("cm_action_enabled")),
            "cm_enforcement_allow": bool(comment_decision["allow"]),
            "cm_enforcement_reason": comment_decision["reason"],
            "readiness": comment_decision["readiness"],
            "live_verified": False,
        }
        connections.append(public)

    authorizations: dict[str, dict[str, Any]] = {}
    for connection in connections:
        auth_key = str(connection.get("authorized_meta_user_id_hash") or "unknown")
        bucket = authorizations.setdefault(
            auth_key,
            {
                "authorized_meta_user_id_hash": auth_key if auth_key != "unknown" else "",
                "app_key": connection.get("app_key"),
                "app_label": connection.get("app_label"),
                "authorization_title": _authorization_title(connection.get("app_key")),
                "assets": [],
            },
        )
        bucket["assets"].append(connection)
    ig_status = instagram_login_config_status()
    return {
        "success": True,
        "registry_enabled": True,
        "instagram_login_configured": ig_status.configured,
        "instagram_login_config": {
            "configured": ig_status.configured,
            "missing": list(ig_status.missing),
            "reasons": ig_status.reasons,
        },
        "apps": [config.public_dict() for config in get_meta_app_configs().values()],
        "connections": connections,
        "authorizations": list(authorizations.values()),
    }


@app.post("/api/meta/connections/start")
async def start_meta_connection(
    request: Request,
    body: dict[str, Any] = Body(default={}),
) -> Any:
    session = require_permission(request, "settings")
    channel = str(body.get("channel") or "unified").strip().lower()
    if channel not in {"facebook", "instagram", "unified", "meta", ""}:
        raise HTTPException(status_code=400, detail="channel must be facebook, instagram, or unified")
    return_surface = normalize_return_surface(body.get("return_surface"))
    try:
        login_url = begin_meta_business_login(
            tenant_id=session.tenant_id,
            channel=normalize_oauth_flow_channel(channel),
            actor_id=session.user_id or session.email,
            return_surface=return_surface,
        )
    except (MetaOAuthError, MetaRegistryError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"success": True, "authorization_url": login_url}


@app.post("/api/meta/connections/instagram-login/start")
async def start_instagram_login_connection(
    request: Request,
    body: dict[str, Any] = Body(default={}),
) -> Any:
    session = require_permission(request, "settings")
    return_surface = normalize_return_surface(body.get("return_surface"))
    try:
        login_url = begin_instagram_login(
            tenant_id=session.tenant_id,
            actor_id=session.user_id or session.email,
            return_surface=return_surface,
        )
    except (MetaOAuthError, MetaRegistryError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"success": True, "authorization_url": login_url}


@app.get("/oauth/instagram/callback")
async def instagram_login_oauth_callback(
    code: str = Query(default=""),
    state: str = Query(default=""),
    error: str = Query(default=""),
) -> RedirectResponse:
    from services.meta_app_registry import MetaOAuthStateError

    if _query_text(error):
        surface = consume_return_surface_from_state(_query_text(state))
        return RedirectResponse(
            url=oauth_completion_redirect_url(
                return_surface=surface,
                meta_connection="cancelled",
                extra_query={"meta_flow": "instagram_login"},
            ),
            status_code=303,
        )
    try:
        result = await complete_instagram_login(code=_query_text(code), state=_query_text(state))
        return RedirectResponse(
            url=oauth_completion_redirect_url(
                return_surface=result.return_surface,
                meta_connection="connected",
                extra_query={
                    "meta_flow": "instagram_login",
                    "channel": result.binding.channel,
                    "status": result.binding.status,
                },
            ),
            status_code=303,
        )
    except (MetaOAuthError, MetaOAuthStateError, MetaRegistryError):
        surface = consume_return_surface_from_state(_query_text(state))
        return RedirectResponse(
            url=oauth_completion_redirect_url(
                return_surface=surface,
                meta_connection="failed",
                extra_query={"meta_flow": "instagram_login"},
            ),
            status_code=303,
        )


@app.get("/oauth/meta/callback")
async def meta_oauth_callback(
    code: str = Query(default=""),
    state: str = Query(default=""),
    error: str = Query(default=""),
) -> RedirectResponse:
    """Public Meta redirect; one-time state is the authorization boundary."""

    if _query_text(error):
        surface = consume_return_surface_from_state(_query_text(state))
        return RedirectResponse(
            url=oauth_completion_redirect_url(
                return_surface=surface,
                meta_connection="cancelled",
            ),
            status_code=303,
        )
    try:
        result = await complete_meta_business_login(code=_query_text(code), state=_query_text(state))
        return RedirectResponse(
            url=oauth_completion_redirect_url(
                return_surface=result.return_surface,
                meta_connection="connected",
                extra_query={
                    "channel": result.binding.channel,
                    "status": result.binding.status,
                    "connected_count": str(len(result.bindings)),
                },
            ),
            status_code=303,
        )
    except (MetaOAuthError, MetaRegistryError):
        surface = consume_return_surface_from_state(_query_text(state))
        return RedirectResponse(
            url=oauth_completion_redirect_url(
                return_surface=surface,
                meta_connection="failed",
            ),
            status_code=303,
        )


@app.post("/api/meta/connections/{binding_id}/disconnect")
async def disconnect_meta_connection(binding_id: str, request: Request) -> Any:
    session = require_permission(request, "settings")
    binding = _tenant_binding(binding_id, session.tenant_id)
    try:
        if binding.active:
            updated = await disconnect_binding_webhook(
                binding,
                actor_id=session.user_id or session.email,
            )
        else:
            updated = get_meta_app_registry().set_binding_status(
                binding.binding_id,
                status="disconnected",
                actor_id=session.user_id or session.email,
                expected_generation=binding.generation,
            )
    except (MetaOAuthError, MetaRegistryError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
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
    """Re-enable a disconnected first-party (App A) binding when its token is still valid."""

    session = require_permission(request, "settings")
    binding = _tenant_binding(binding_id, session.tenant_id)
    if binding.app_key != APP_A_KEY:
        raise HTTPException(
            status_code=409,
            detail=(
                "Reconnect is only for stored Lina Meta app bindings. "
                "Use Add / Manage Facebook & Instagram to authorize a Page again."
            ),
        )
    if binding.auth_flow == "instagram_login":
        raise HTTPException(
            status_code=409,
            detail="Reconnect Instagram Login connections with Connect Instagram.",
        )
    if binding.status not in {"disconnected", "inactive"}:
        raise HTTPException(status_code=409, detail="Connection is already active or cannot be reconnected here")
    registry = get_meta_app_registry()
    try:
        credential = registry.get_credential(binding)
        now = int(time.time())
        if credential.expires_at is not None and credential.expires_at <= now:
            raise HTTPException(
                status_code=409,
                detail="Stored Meta token expired. Ask ops to re-apply App A credentials.",
            )
    except MetaRegistryError as exc:
        raise HTTPException(
            status_code=409,
            detail="Stored Meta token is unavailable. Ask ops to re-apply App A credentials.",
        ) from exc
    try:
        previous = _active_conflict(binding)
        if previous is not None:
            raise HTTPException(status_code=409, detail="Another active binding owns this channel or asset")
        staged = MetaAssetBinding(**{**binding.__dict__, "status": "active"})
        await subscribe_binding_webhook(staged, registry=registry)
        try:
            updated = registry.set_binding_status(
                binding.binding_id,
                status="active",
                actor_id=session.user_id or session.email,
                expected_generation=binding.generation,
            )
        except MetaRegistryError:
            await unsubscribe_binding_webhook(staged, registry=registry)
            raise
    except (MetaOAuthError, MetaRegistryError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"success": True, "connection": updated.public_dict()}


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
                "Missing Meta comment permissions. Re-authorize with Manage Meta Access "
                "(Facebook Connect uses the Facebook-only Login Configuration)."
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
