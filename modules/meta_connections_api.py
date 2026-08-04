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
    APP_B_KEY,
    MetaAssetBinding,
    MetaRegistryError,
    get_meta_app_configs,
    get_meta_app_registry,
    meta_multi_app_registry_enabled,
)
from services.meta_oauth import (
    MetaOAuthError,
    begin_meta_business_login,
    complete_meta_business_login,
    disconnect_binding_webhook,
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
        for item in get_meta_app_registry().list_bindings(include_inactive=False)
        if item.binding_id != binding.binding_id
        and (
            (item.tenant_id == binding.tenant_id and item.channel == binding.channel)
            or (item.channel == binding.channel and item.asset_id == binding.asset_id)
        )
    ]
    if len(matches) > 1:
        raise MetaRegistryError("Active Meta binding indexes are inconsistent")
    return matches[0] if matches else None


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
    connections: list[dict[str, Any]] = []
    for binding in registry.list_bindings():
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
        except MetaRegistryError:
            public["token_status"] = "unavailable"
            public["expires_at"] = None
            public["granted_permissions"] = []
        connections.append(public)
    return {
        "success": True,
        "registry_enabled": True,
        "apps": [config.public_dict() for config in get_meta_app_configs().values()],
        "connections": connections,
    }


@app.post("/api/meta/connections/start")
async def start_meta_connection(
    request: Request,
    body: dict[str, Any] = Body(default={}),
) -> Any:
    session = require_permission(request, "settings")
    channel = str(body.get("channel") or "").strip().lower()
    if channel not in {"facebook", "instagram"}:
        raise HTTPException(status_code=400, detail="channel must be facebook or instagram")
    try:
        login_url = begin_meta_business_login(
            tenant_id=session.tenant_id,
            channel=channel,  # type: ignore[arg-type]
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


@app.post("/api/meta/connections/{binding_id}/activate")
async def activate_meta_connection(binding_id: str, request: Request) -> Any:
    session = require_permission(request, "settings")
    binding = _tenant_binding(binding_id, session.tenant_id)
    if binding.app_key != APP_B_KEY or binding.status not in {"testing", "inactive"}:
        raise HTTPException(status_code=409, detail="Connection is not eligible for activation")
    if session.tenant_id != "linas":
        from services.cm.constants import cm_runtime_mode
        from services.cm.version_store import load_published_content

        if cm_runtime_mode() != "published":
            raise HTTPException(status_code=409, detail="Tenant AI content is not in published mode")
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
