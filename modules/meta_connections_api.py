"""Authenticated, tenant-isolated control plane for Meta App B connections."""

from __future__ import annotations

import time
from typing import Any

from fastapi import Body, HTTPException, Query, Request

from modules.api_security import require_permission
from modules.core import app
from modules.meta_connections_api_helpers import (  # noqa: F401
    _active_conflict,
    _authorization_title,
    _query_text,
    _subscription_identity,
    _tenant_binding,
)
from services.meta_app_registry import (  # noqa: F401 — re-exports for lifecycle/tests
    APP_A_KEY,
    APP_B_KEY,
    MetaAssetBinding,
    MetaRegistryError,
    _bindings_share_exclusive_asset,
    get_meta_app_configs,
    get_meta_app_registry,
    meta_multi_app_registry_enabled,
)
from services.meta_comment_reply_settings import get_comment_reply_setting, set_comment_reply_setting  # noqa: F401
from services.meta_comment_webhooks import (  # noqa: F401 — re-exports for lifecycle/tests
    credential_has_comment_scopes,
    ensure_instagram_comment_app_webhook,
    ensure_page_comment_webhook_subscription,
    required_comment_scopes,
)
from services.meta_graph_routing import required_comment_scopes_for_binding
from services.meta_instagram_login_config import instagram_login_config_status
from services.meta_instagram_login_oauth import begin_instagram_login, complete_instagram_login
from services.meta_instagram_login_subscription_recovery import (  # noqa: F401
    retry_instagram_login_webhook_subscription,
)
from services.meta_oauth import (  # noqa: F401 — re-exports patched by tests / used by lifecycle
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
    mobile_oauth_failure_reason,
    normalize_return_surface,
    oauth_completion_response,
    peek_return_surface_from_state,
)


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
            binding=binding,
            credential=credential,
            registry=registry,
        )
        public["comment_replies"] = {
            **comment_setting.public_dict(),
            "scopes_granted": sorted(
                required_comment_scopes_for_binding(binding) & set(public.get("granted_permissions") or [])
            ),
            "scopes_required": sorted(required_comment_scopes_for_binding(binding)),
            "scopes_ready": bool(comment_decision.get("permission", {}).get("status") == "verified_granted"),
            "permission": comment_decision.get("permission") or {},
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
    # Default to Facebook Pages Connect. Instagram must use /instagram-login/start.
    channel = str(body.get("channel") or "facebook").strip().lower()
    if channel in {"instagram"}:
        raise HTTPException(
            status_code=400,
            detail=(
                "Instagram Connect uses Instagram Login. POST /api/meta/connections/instagram-login/start instead."
            ),
        )
    if channel not in {"facebook", "unified", "meta", ""}:
        raise HTTPException(status_code=400, detail="channel must be facebook for Business Login")
    return_surface = normalize_return_surface(body.get("return_surface"))
    try:
        flow_channel = "facebook" if channel in {"", "meta", "unified"} else channel
        login_url = begin_meta_business_login(
            tenant_id=session.tenant_id,
            channel=normalize_oauth_flow_channel(flow_channel),
            actor_id=session.user_id or session.email,
            return_surface=return_surface,
        )
    except (MetaOAuthError, MetaRegistryError) as exc:
        detail: str | dict[str, str] = str(exc)
        if return_surface == "mobile":
            detail = {"meta_reason": mobile_oauth_failure_reason(exc)}
        raise HTTPException(status_code=503, detail=detail) from exc
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
        detail: str | dict[str, str] = str(exc)
        if return_surface == "mobile":
            detail = {"meta_reason": mobile_oauth_failure_reason(exc)}
        raise HTTPException(status_code=503, detail=detail) from exc
    return {"success": True, "authorization_url": login_url}


@app.get("/oauth/instagram/callback")
async def instagram_login_oauth_callback(
    code: str = Query(default=""),
    state: str = Query(default=""),
    error: str = Query(default=""),
) -> Any:
    import logging

    from services.meta_app_registry import MetaOAuthStateError
    from services.meta_oauth_return import mobile_oauth_failure_reason, resolve_error_return_surface

    logger = logging.getLogger("meta_oauth.callback")
    state_text = _query_text(state)
    code_text = _query_text(code)
    error_text = _query_text(error)
    peeked = peek_return_surface_from_state(state_text)
    if error_text:
        surface = consume_return_surface_from_state(state_text) if state_text else peeked
        logger.warning(
            "instagram_login_callback cancelled error=%s surface=%s has_state=%s",
            error_text[:80],
            surface,
            bool(state_text),
        )
        return oauth_completion_response(
            return_surface=surface,
            meta_connection="cancelled",
            extra_query={"meta_flow": "instagram_login", "channel": "instagram"},
        )
    try:
        result = await complete_instagram_login(code=code_text, state=state_text)
        logger.info(
            "instagram_login_callback connected surface=%s channel=%s status=%s",
            result.return_surface,
            result.binding.channel,
            result.binding.status,
        )
        return oauth_completion_response(
            return_surface=result.return_surface,
            meta_connection="connected",
            extra_query={
                "meta_flow": "instagram_login",
                "channel": result.binding.channel,
                "status": result.binding.status,
            },
        )
    except (MetaOAuthError, MetaOAuthStateError, MetaRegistryError) as exc:
        surface = resolve_error_return_surface(exc, state_text, peeked=peeked)
        reason = mobile_oauth_failure_reason(exc)
        logger.warning(
            "instagram_login_callback failed type=%s reason=%s msg=%s surface=%s has_code=%s has_state=%s",
            type(exc).__name__,
            reason,
            str(exc)[:200],
            surface,
            bool(code_text),
            bool(state_text),
        )
        return oauth_completion_response(
            return_surface=surface,
            meta_connection="failed",
            extra_query={"meta_flow": "instagram_login", "meta_reason": reason, "channel": "instagram"},
        )


@app.get("/oauth/meta/callback")
async def meta_oauth_callback(
    code: str = Query(default=""),
    state: str = Query(default=""),
    error: str = Query(default=""),
) -> Any:
    """Public Meta redirect; one-time state is the authorization boundary."""

    import logging

    from services.meta_app_registry import MetaOAuthStateError
    from services.meta_oauth_return import mobile_oauth_failure_reason, resolve_error_return_surface

    logger = logging.getLogger("meta_oauth.callback")
    state_text = _query_text(state)
    code_text = _query_text(code)
    error_text = _query_text(error)
    peeked = peek_return_surface_from_state(state_text)
    if error_text:
        surface = consume_return_surface_from_state(state_text) if state_text else peeked
        logger.warning(
            "meta_oauth_callback cancelled error=%s surface=%s has_state=%s",
            error_text[:80],
            surface,
            bool(state_text),
        )
        return oauth_completion_response(
            return_surface=surface,
            meta_connection="cancelled",
            extra_query={"channel": "facebook"},
        )
    try:
        result = await complete_meta_business_login(code=code_text, state=state_text)
        return oauth_completion_response(
            return_surface=result.return_surface,
            meta_connection="connected",
            extra_query={
                "channel": result.binding.channel,
                "status": result.binding.status,
                "connected_count": str(len(result.bindings)),
            },
        )
    except (MetaOAuthError, MetaOAuthStateError, MetaRegistryError) as exc:
        surface = resolve_error_return_surface(exc, state_text, peeked=peeked)
        reason = mobile_oauth_failure_reason(exc)
        # Safe diagnostics only: never log code/state/tokens.
        logger.warning(
            "meta_oauth_callback failed type=%s reason=%s msg=%s surface=%s has_code=%s has_state=%s peeked=%s",
            type(exc).__name__,
            reason,
            str(exc)[:200],
            surface,
            bool(code_text),
            bool(state_text),
            peeked,
        )
        return oauth_completion_response(
            return_surface=surface,
            meta_connection="failed",
            extra_query={"meta_reason": reason, "channel": "facebook"},
        )


# Register disconnect/reconnect/activate/rollback/comment-replies routes
# and re-export lifecycle handlers for tests / direct callers.
from modules import meta_connections_api_lifecycle  # noqa: E402, F401
from modules.meta_connections_api_lifecycle import (  # noqa: E402, F401
    activate_meta_connection,
    disconnect_meta_connection,
    reconnect_meta_connection,
    rollback_meta_connection,
    update_meta_comment_replies,
)
