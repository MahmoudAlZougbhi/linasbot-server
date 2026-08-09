"""Authenticated, tenant-isolated control plane for Meta App B connections."""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import urlencode

from fastapi import Body, HTTPException, Query, Request
from fastapi.responses import RedirectResponse

from modules.api_security import require_permission
from modules.core import app
from services.meta_app_registry import (
    APP_A_KEY,
    APP_B_KEY,
    MetaAssetBinding,
    MetaRegistryError,
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
from services.meta_oauth import (
    MetaOAuthError,
    begin_meta_business_login,
    complete_meta_business_login,
    disconnect_binding_webhook,
    normalize_oauth_flow_channel,
    subscribe_binding_webhook,
    unsubscribe_binding_webhook,
)


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
        and item.channel == binding.channel
        and item.asset_id == binding.asset_id
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
            if not public.get("authorized_meta_user_id_hash"):
                from services.meta_app_registry import authorized_meta_user_id_hash

                public["authorized_meta_user_id_hash"] = authorized_meta_user_id_hash(
                    credential.authorized_meta_user_id
                )
        except MetaRegistryError:
            public["token_status"] = "unavailable"
            public["expires_at"] = None
            public["granted_permissions"] = []
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
                required_comment_scopes(binding.channel) & set(public.get("granted_permissions") or [])
            ),
            "scopes_required": sorted(required_comment_scopes(binding.channel)),
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
    return {
        "success": True,
        "registry_enabled": True,
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
    try:
        login_url = begin_meta_business_login(
            tenant_id=session.tenant_id,
            channel=normalize_oauth_flow_channel(channel),
            actor_id=session.user_id or session.email,
        )
    except (MetaOAuthError, MetaRegistryError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"success": True, "authorization_url": login_url}


@app.get("/oauth/meta/callback")
async def meta_oauth_callback(
    code: str = Query(default=""),
    state: str = Query(default=""),
    error: str = Query(default=""),
) -> RedirectResponse:
    """Public Meta redirect; one-time state is the authorization boundary."""

    if error:
        query = urlencode({"meta_connection": "cancelled"})
        return RedirectResponse(url=f"/settings?{query}", status_code=303)
    try:
        result = await complete_meta_business_login(code=code, state=state)
        query = urlencode(
            {
                "meta_connection": "connected",
                "channel": result.binding.channel,
                "status": result.binding.status,
                "connected_count": str(len(result.bindings)),
            }
        )
    except (MetaOAuthError, MetaRegistryError):
        query = urlencode({"meta_connection": "failed"})
    return RedirectResponse(url=f"/settings?{query}", status_code=303)


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
    if enabled and not credential_has_comment_scopes(binding):
        raise HTTPException(
            status_code=409,
            detail=(
                "Missing Meta comment permissions. Re-authorize with Add / Manage Facebook & Instagram "
                "after the new permissions are added to Login Configuration 1057282070324984."
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
                    "Enable the matching Comments action in Content Management → Actions "
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
